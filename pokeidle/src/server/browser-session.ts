import { chmod, mkdir, readdir, readFile } from "node:fs/promises";
import { dirname } from "node:path";
import { chromium, type BrowserContext, type CDPSession, type Page } from "playwright";
import type { AppConfig, InstanceConfig } from "./config.js";
import { contractIsComplete, instanceProfileDir } from "./config.js";
import {
  assertAccessibleTargetMatches,
  assertAccessibleTargetSafe,
  assertSelectorPolicy,
  sanitizeUrl,
  type AllowedGameAction,
} from "./security.js";
import type { GameObservation, MetricSample } from "./types.js";
import type { SafeLogger } from "./logger.js";

interface CpuSample {
  atMs: number;
  cpuSeconds: number;
}

export class BrowserSession {
  readonly #config: AppConfig;
  readonly #instance: InstanceConfig;
  readonly #logger: SafeLogger;
  #context: BrowserContext | null = null;
  #page: Page | null = null;
  #pageCdp: CDPSession | null = null;
  #websocketCount = 0;
  #hasSeenWebsocket = false;
  #crashed = false;
  #previousCpu: CpuSample | null = null;
  #domDirty: (() => void) | null = null;

  constructor(config: AppConfig, instance: InstanceConfig, logger: SafeLogger) {
    this.#config = config;
    this.#instance = instance;
    this.#logger = logger;
  }

  async launch(onDomDirty: () => void): Promise<void> {
    this.#domDirty = onDomDirty;
    this.#crashed = false;
    this.#websocketCount = 0;
    this.#hasSeenWebsocket = false;
    const profileDir = instanceProfileDir(this.#config, this.#instance.id);
    await mkdir(profileDir, { recursive: true, mode: 0o700 });
    this.#context = await chromium.launchPersistentContext(profileDir, {
      headless: true,
      viewport: this.#config.browser.viewport,
      serviceWorkers: "allow",
      args: ["--mute-audio", "--disable-extensions", "--no-first-run", "--no-default-browser-check"],
    });
    const pages = this.#context.pages();
    this.#page = pages[0] ?? (await this.#context.newPage());
    for (const extraPage of pages.slice(1)) await extraPage.close();
    this.#context.on("page", (popup) => {
      if (popup !== this.#page) {
        this.#logger.warn("unexpected_page_closed", { instanceId: this.#instance.id });
        void popup.close();
      }
    });
    await this.#configureResourcePolicy();
    this.#wireDiagnostics(this.#page);
    this.#pageCdp = await this.#context.newCDPSession(this.#page);
    await this.#page.goto(this.#config.game.playUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await this.#installObserver();
  }

  async close(): Promise<void> {
    const context = this.#context;
    this.#context = null;
    this.#page = null;
    this.#pageCdp = null;
    this.#crashed = false;
    this.#websocketCount = 0;
    this.#hasSeenWebsocket = false;
    if (context) await context.close().catch(() => undefined);
  }

  isOpen(): boolean {
    return this.#page !== null && !this.#page.isClosed() && !this.#crashed;
  }

  async observe(): Promise<GameObservation> {
    const page = this.#requirePage();
    const selectors = this.#instance.selectors;
    const contractComplete = contractIsComplete(this.#instance);
    if (!contractComplete) return this.#unknownObservation(false);
    return {
      contractComplete,
      gameReady: await this.#visibleUnique(page, selectors.gameReady),
      loginRequired: await this.#visibleUnique(page, selectors.loginRequired),
      characterPresent: await this.#visibleUnique(page, selectors.characterRoot),
      characterFainted: await this.#visibleUnique(page, selectors.characterFainted),
      hpPercent: await this.#readHp(page, selectors.characterHp),
      huntActive: await this.#visibleUnique(page, selectors.huntActive),
      suppliesMissing: await this.#visibleUnique(page, selectors.suppliesMissing),
      autoPotionEnabled: this.#instance.helpers.autoPotion
        ? await this.#optionalVisible(page, selectors.autoPotionEnabled)
        : true,
      autoReviveEnabled: this.#instance.helpers.autoRevive
        ? await this.#optionalVisible(page, selectors.autoReviveEnabled)
        : true,
      connected: await this.#connectionHealthy(page),
    };
  }

  async configureNativeHelpers(): Promise<boolean> {
    const before = await this.observe();
    let changed = false;
    if (this.#instance.helpers.autoPotion && before.autoPotionEnabled === null) {
      throw new Error("POLICY_BLOCK: estado do Auto-Potion é ambíguo");
    }
    if (this.#instance.helpers.autoPotion && before.autoPotionEnabled === false) {
      await this.#safeClick("activate_auto_potion");
      changed = true;
    }
    if (this.#instance.helpers.autoRevive && before.autoReviveEnabled === null) {
      throw new Error("POLICY_BLOCK: estado do Auto-Revive é ambíguo");
    }
    if (this.#instance.helpers.autoRevive && before.autoReviveEnabled === false) {
      await this.#safeClick("activate_auto_revive");
      changed = true;
    }
    if (changed) await this.#requirePage().waitForTimeout(1_000);
    const after = await this.observe();
    return (
      (!this.#instance.helpers.autoPotion || after.autoPotionEnabled === true) &&
      (!this.#instance.helpers.autoRevive || after.autoReviveEnabled === true)
    );
  }

  async startOrResumeHunt(): Promise<void> {
    const { huntResume, huntStart } = this.#instance.selectors;
    const resumeVisible = huntResume ? await this.#optionalVisible(this.#requirePage(), huntResume) : false;
    if (resumeVisible === null) throw new Error("POLICY_BLOCK: alvo de retomar hunt é ambíguo");
    if (resumeVisible) {
      await this.#safeClick("resume_hunt");
      return;
    }
    if (!huntStart) throw new Error("POLICY_BLOCK: hunt não pode ser iniciada com o contrato atual");
    await this.#safeClick("start_hunt");
  }

  async recoverConnection(): Promise<void> {
    await this.#requirePage().reload({ waitUntil: "domcontentloaded", timeout: 60_000 });
    await this.#installObserver();
  }

  async sampleMetrics(): Promise<MetricSample> {
    const memory = process.memoryUsage();
    const [performanceMetrics, domCounters, processInfo, linuxTree] = await Promise.all([
      this.#pageCdp?.send("Performance.getMetrics").catch(() => null) ?? null,
      this.#pageCdp?.send("Memory.getDOMCounters").catch(() => null) ?? null,
      this.#pageCdp?.send("SystemInfo.getProcessInfo").catch(() => null) ?? null,
      readLinuxChromiumTreeMetrics(process.pid),
    ]);
    const chromiumRss = linuxTree?.rssMb ?? null;
    const cpuSeconds = linuxTree?.cpuSeconds ??
      (processInfo?.processInfo.reduce((total, item) => total + item.cpuTime, 0) ?? null);
    const now = Date.now();
    let chromiumCpuPercent: number | null = null;
    if (cpuSeconds !== null && this.#previousCpu) {
      const wallSeconds = (now - this.#previousCpu.atMs) / 1000;
      chromiumCpuPercent = wallSeconds > 0 ? ((cpuSeconds - this.#previousCpu.cpuSeconds) / wallSeconds) * 100 : null;
    }
    if (cpuSeconds !== null) this.#previousCpu = { atMs: now, cpuSeconds };
    const metrics = performanceMetrics?.metrics ?? [];
    const jsHeapBytes = metrics.find((item) => item.name === "JSHeapUsedSize")?.value ?? null;
    return {
      at: new Date(now).toISOString(),
      nodeRssMb: bytesToMb(memory.rss),
      nodeHeapMb: bytesToMb(memory.heapUsed),
      chromiumRssMb: chromiumRss,
      chromiumCpuPercent: chromiumCpuPercent === null ? null : round(chromiumCpuPercent),
      jsHeapMb: jsHeapBytes === null ? null : bytesToMb(jsHeapBytes),
      domNodes: domCounters?.nodes ?? null,
      websocketCount: this.#websocketCount,
    };
  }

  pageCount(): number {
    return this.#context?.pages().length ?? 0;
  }

  async screenshotOnError(path: string, allowed: boolean): Promise<void> {
    if (!allowed) return;
    const page = this.#page;
    if (!page || page.isClosed()) return;
    const observation = await this.observe().catch(() => null);
    if (observation?.loginRequired !== false || observation.suppliesMissing !== false) return;
    await mkdir(dirname(path), { recursive: true, mode: 0o700 });
    const captured = await page.screenshot({ path, fullPage: false }).then(() => true).catch(() => false);
    if (captured) await chmod(path, 0o600).catch(() => undefined);
  }

  async #safeClick(action: AllowedGameAction): Promise<void> {
    const { selector, expectedAccessibleName } = this.#actionContract(action);
    assertSelectorPolicy(selector);
    if (!selector) throw new Error(`Contrato DOM ausente para ${action}`);
    assertAccessibleTargetSafe(expectedAccessibleName);
    const page = this.#requirePage();
    const locator = page.locator(selector);
    const count = await locator.count();
    if (count !== 1) throw new Error(`Contrato DOM ambíguo para ${action}: ${count} alvos`);
    const namedButton = page.getByRole("button", { name: expectedAccessibleName, exact: true });
    const namedCount = await namedButton.count();
    const verifiedTarget = locator.and(namedButton);
    if (namedCount !== 1 || await verifiedTarget.count() !== 1) {
      throw new Error(`POLICY_BLOCK: identidade acessível divergente para ${action}`);
    }
    assertAccessibleTargetMatches(expectedAccessibleName, expectedAccessibleName);
    const target = verifiedTarget.first();
    const safetyText = await target.evaluate((element) => {
      const htmlElement = element as HTMLElement;
      const labelledBy = (element.getAttribute("aria-labelledby") ?? "")
        .split(/\s+/)
        .filter(Boolean)
        .map((id) => document.getElementById(id)?.textContent ?? "");
      const descendants = Array.from(element.querySelectorAll<HTMLElement>("[aria-label], [title], img[alt], input[value]"))
        .flatMap((child) => [child.getAttribute("aria-label"), child.getAttribute("title"), child.getAttribute("alt"), child.getAttribute("value")]);
      return [htmlElement.innerText, element.textContent, element.getAttribute("aria-label"), element.getAttribute("title"), element.getAttribute("alt"), ...labelledBy, ...descendants]
        .filter(Boolean)
        .join(" ");
    });
    assertAccessibleTargetSafe(safetyText);
    await target.click({ timeout: 10_000 });
    this.#logger.info("game_action", { instanceId: this.#instance.id, action });
  }

  async #configureResourcePolicy(): Promise<void> {
    if (!this.#context) return;
    const blocked = new Set(this.#config.browser.resources.blockedUrlPatterns);
    await this.#context.route("**/*", async (route) => {
      const request = route.request();
      const type = request.resourceType();
      const blockMedia = this.#config.browser.resources.blockMedia && type === "media";
      const exactBlockedAsset =
        blocked.has(sanitizeUrl(request.url())) && ["image", "font", "stylesheet"].includes(type);
      if (blockMedia || exactBlockedAsset) await route.abort("blockedbyclient");
      else await route.continue();
    });
  }

  #wireDiagnostics(page: Page): void {
    page.on("websocket", (socket) => {
      this.#hasSeenWebsocket = true;
      this.#websocketCount += 1;
      socket.on("close", () => {
        this.#websocketCount = Math.max(0, this.#websocketCount - 1);
        this.#domDirty?.();
      });
    });
    page.on("crash", () => {
      this.#crashed = true;
      this.#domDirty?.();
    });
    page.on("close", () => this.#domDirty?.());
    page.on("domcontentloaded", () => void this.#installObserver());
  }

  async #installObserver(): Promise<void> {
    const page = this.#requirePage();
    await page.exposeBinding("__pokeIdleDomDirty", () => this.#domDirty?.()).catch(() => undefined);
    await page.evaluate(() => {
      const globalWindow = window as Window & Record<string, unknown>;
      if (globalWindow.__pokeIdleObserverInstalled) return;
      globalWindow.__pokeIdleObserverInstalled = true;
      let timer: number | undefined;
      const observer = new MutationObserver(() => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => {
          (window as Window & { __pokeIdleDomDirty?: () => void }).__pokeIdleDomDirty?.();
        }, 1_000);
      });
      observer.observe(document.documentElement, {
        subtree: true,
        childList: true,
        attributes: true,
        characterData: true,
      });
    });
  }

  async #visibleUnique(page: Page, selector: string): Promise<boolean | null> {
    const locator = page.locator(selector);
    const count = await locator.count();
    if (count > 1) return null;
    if (count === 0) return false;
    return locator.first().isVisible();
  }

  async #optionalVisible(page: Page, selector: string): Promise<boolean | null> {
    return selector ? this.#visibleUnique(page, selector) : null;
  }

  async #connectionHealthy(page: Page): Promise<boolean> {
    if (page.isClosed() || this.#crashed) return false;
    const online = await page.evaluate(() => navigator.onLine).catch(() => false);
    return online && (!this.#hasSeenWebsocket || this.#websocketCount > 0);
  }

  #actionContract(action: AllowedGameAction): { selector: string; expectedAccessibleName: string } {
    switch (action) {
      case "activate_auto_potion":
        return { selector: this.#instance.selectors.autoPotionToggle, expectedAccessibleName: this.#instance.expectedAccessibleNames.autoPotionToggle };
      case "activate_auto_revive":
        return { selector: this.#instance.selectors.autoReviveToggle, expectedAccessibleName: this.#instance.expectedAccessibleNames.autoReviveToggle };
      case "start_hunt":
        return { selector: this.#instance.selectors.huntStart, expectedAccessibleName: this.#instance.expectedAccessibleNames.huntStart };
      case "resume_hunt":
        return { selector: this.#instance.selectors.huntResume, expectedAccessibleName: this.#instance.expectedAccessibleNames.huntResume };
    }
  }

  async #readHp(page: Page, selector: string): Promise<number | null> {
    const locator = page.locator(selector);
    if ((await locator.count()) !== 1) return null;
    const raw = await locator.first().evaluate((element) =>
      [element.getAttribute("aria-valuenow"), element.getAttribute("data-hp-percent"), element.textContent]
        .filter(Boolean)
        .join(" "),
    );
    const match = raw.match(/(?:^|\s)(100|\d{1,2})(?:[.,]\d+)?\s*%?(?:\s|$)/);
    return match?.[1] ? Math.max(0, Math.min(100, Number(match[1]))) : null;
  }

  #unknownObservation(contractComplete: boolean): GameObservation {
    return {
      contractComplete,
      gameReady: null,
      loginRequired: null,
      characterPresent: null,
      characterFainted: null,
      hpPercent: null,
      huntActive: null,
      suppliesMissing: null,
      autoPotionEnabled: null,
      autoReviveEnabled: null,
      connected: this.isOpen(),
    };
  }

  #requirePage(): Page {
    if (!this.#page || this.#page.isClosed()) throw new Error("Página oficial indisponível");
    return this.#page;
  }
}

function bytesToMb(bytes: number): number {
  return round(bytes / 1024 / 1024);
}

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

async function readLinuxChromiumTreeMetrics(rootPid: number): Promise<{ rssMb: number; cpuSeconds: number } | null> {
  if (process.platform !== "linux") return null;
  try {
    const entries = (await readdir("/proc")).filter((entry) => /^\d+$/.test(entry));
    const processes: Array<{ pid: number; ppid: number; rssKb: number; cpuTicks: number }> = [];
    for (const entry of entries) {
      const status = await readFile(`/proc/${entry}/status`, "utf8").catch(() => "");
      const stat = await readFile(`/proc/${entry}/stat`, "utf8").catch(() => "");
      const ppid = Number(status.match(/^PPid:\s+(\d+)/m)?.[1] ?? -1);
      const rssKb = Number(status.match(/^VmRSS:\s+(\d+)/m)?.[1] ?? 0);
      const statFields = stat.slice(stat.lastIndexOf(")") + 2).split(/\s+/);
      const cpuTicks = Number(statFields[11] ?? 0) + Number(statFields[12] ?? 0);
      processes.push({ pid: Number(entry), ppid, rssKb, cpuTicks });
    }
    const included = new Set([rootPid]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const item of processes) {
        if (included.has(item.ppid) && !included.has(item.pid)) {
          included.add(item.pid);
          changed = true;
        }
      }
    }
    const chromiumProcesses = processes.filter((item) => item.pid !== rootPid && included.has(item.pid));
    if (chromiumProcesses.length === 0) return null;
    const rssKb = chromiumProcesses.reduce((sum, item) => sum + item.rssKb, 0);
    const cpuTicks = chromiumProcesses.reduce((sum, item) => sum + item.cpuTicks, 0);
    return { rssMb: round(rssKb / 1024), cpuSeconds: cpuTicks / 100 };
  } catch {
    return null;
  }
}
