import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { parse as parseYaml } from "yaml";
import { assertAccessibleTargetSafe, assertSelectorPolicy, sanitizeUrl } from "./security.js";

export interface SelectorsConfig {
  gameReady: string;
  loginRequired: string;
  characterRoot: string;
  characterFainted: string;
  characterHp: string;
  huntActive: string;
  huntStart: string;
  huntResume: string;
  suppliesMissing: string;
  autoPotionToggle: string;
  autoPotionEnabled: string;
  autoReviveToggle: string;
  autoReviveEnabled: string;
}

export interface ExpectedAccessibleNamesConfig {
  huntStart: string;
  huntResume: string;
  autoPotionToggle: string;
  autoReviveToggle: string;
}

export interface InstanceConfig {
  id: string;
  enabled: boolean;
  accountLabel: string;
  environment: string;
  helpers: { autoPotion: boolean; autoRevive: boolean };
  selectors: SelectorsConfig;
  expectedAccessibleNames: ExpectedAccessibleNamesConfig;
}

export interface AppConfig {
  schemaVersion: 1;
  game: {
    name: "Poke Idle World";
    url: "https://poke.idleworld.online";
    playUrl: "https://poke.idleworld.online/play";
    rulesAcknowledged: boolean;
  };
  runtime: { executionMode: "persistent_headless"; dataDir: string };
  browser: {
    headless: true;
    maxPages: 1;
    viewport: { width: number; height: number };
    resources: { blockMedia: boolean; blockedUrlPatterns: string[] };
  };
  supervisor: {
    heartbeatSeconds: number;
    staleAfterSeconds: number;
    maxRestarts: number;
    restartWindowMinutes: number;
    circuitFailures: number;
    circuitWindowMinutes: number;
    circuitCooldownMinutes: number;
    backoffBaseSeconds: number;
    backoffMaxSeconds: number;
  };
  dashboard: { host: string; port: number };
  logging: { level: "debug" | "info" | "warn" | "error"; rotateMegabytes: number; retainFiles: number };
  metrics: { sampleSeconds: number; historySamples: number };
  instances: InstanceConfig[];
}

const ROOT_KEYS = ["schemaVersion", "game", "runtime", "browser", "supervisor", "dashboard", "logging", "metrics", "instances"] as const;
const SELECTOR_KEYS = [
  "gameReady", "loginRequired", "characterRoot", "characterFainted", "characterHp", "huntActive",
  "huntStart", "huntResume", "suppliesMissing", "autoPotionToggle", "autoPotionEnabled",
  "autoReviveToggle", "autoReviveEnabled",
] as const;
const ACTION_KEYS = ["huntStart", "huntResume", "autoPotionToggle", "autoReviveToggle"] as const;

export async function loadConfig(path = process.env.POKEIDLE_CONFIG ?? "config.yaml"): Promise<AppConfig> {
  const parsed: unknown = parseYaml(await readFile(resolve(path), "utf8"));
  return validateConfig(parsed);
}

export function validateConfig(value: unknown): AppConfig {
  const root = record(value, "config");
  exactKeys(root, ROOT_KEYS, "config");
  literal(root.schemaVersion, 1, "schemaVersion");

  const game = record(root.game, "game");
  exactKeys(game, ["name", "url", "playUrl", "rulesAcknowledged"], "game");
  literal(game.name, "Poke Idle World", "game.name");
  literal(game.url, "https://poke.idleworld.online", "game.url");
  literal(game.playUrl, "https://poke.idleworld.online/play", "game.playUrl");

  const runtime = record(root.runtime, "runtime");
  exactKeys(runtime, ["executionMode", "dataDir"], "runtime");
  literal(runtime.executionMode, "persistent_headless", "runtime.executionMode");

  const browser = record(root.browser, "browser");
  exactKeys(browser, ["headless", "maxPages", "viewport", "resources"], "browser");
  literal(browser.headless, true, "browser.headless");
  literal(browser.maxPages, 1, "browser.maxPages");
  const viewport = record(browser.viewport, "browser.viewport");
  exactKeys(viewport, ["width", "height"], "browser.viewport");
  const resources = record(browser.resources, "browser.resources");
  exactKeys(resources, ["blockMedia", "blockedUrlPatterns"], "browser.resources");
  const blockedUrlPatterns = textArray(resources.blockedUrlPatterns, "browser.resources.blockedUrlPatterns");
  if (blockedUrlPatterns.some((url) => !/^https:\/\//i.test(url) || sanitizeUrl(url) !== url)) {
    throw new Error("browser.resources.blockedUrlPatterns aceita somente URLs HTTPS exatas, sem query ou hash");
  }

  const supervisor = record(root.supervisor, "supervisor");
  const supervisorKeys = ["heartbeatSeconds", "staleAfterSeconds", "maxRestarts", "restartWindowMinutes", "circuitFailures", "circuitWindowMinutes", "circuitCooldownMinutes", "backoffBaseSeconds", "backoffMaxSeconds"] as const;
  exactKeys(supervisor, supervisorKeys, "supervisor");

  const dashboard = record(root.dashboard, "dashboard");
  exactKeys(dashboard, ["host", "port"], "dashboard");
  const logging = record(root.logging, "logging");
  exactKeys(logging, ["level", "rotateMegabytes", "retainFiles"], "logging");
  const metrics = record(root.metrics, "metrics");
  exactKeys(metrics, ["sampleSeconds", "historySamples"], "metrics");

  if (!Array.isArray(root.instances) || root.instances.length === 0) throw new Error("instances deve conter pelo menos uma instância");
  const ids = new Set<string>();
  const instances = root.instances.map((rawInstance, index) => {
    const item = record(rawInstance, `instances[${index}]`);
    exactKeys(item, ["id", "enabled", "accountLabel", "environment", "helpers", "selectors", "expectedAccessibleNames"], `instances[${index}]`);
    const id = text(item.id, `instances[${index}].id`);
    if (!/^[a-z0-9][a-z0-9_-]{1,31}$/.test(id)) throw new Error(`ID inválido: ${id}`);
    if (ids.has(id)) throw new Error(`ID de instância duplicado: ${id}`);
    ids.add(id);
    const helpers = record(item.helpers, `instances.${id}.helpers`);
    exactKeys(helpers, ["autoPotion", "autoRevive"], `instances.${id}.helpers`);
    const selectorRecord = record(item.selectors, `instances.${id}.selectors`);
    exactKeys(selectorRecord, SELECTOR_KEYS, `instances.${id}.selectors`);
    const selectors = Object.fromEntries(
      SELECTOR_KEYS.map((key) => {
        const selector = text(selectorRecord[key], `instances.${id}.selectors.${key}`, true);
        assertSelectorPolicy(selector);
        return [key, selector];
      }),
    ) as unknown as SelectorsConfig;
    const accessibleNameRecord = record(item.expectedAccessibleNames, `instances.${id}.expectedAccessibleNames`);
    exactKeys(accessibleNameRecord, ACTION_KEYS, `instances.${id}.expectedAccessibleNames`);
    const expectedAccessibleNames = Object.fromEntries(
      ACTION_KEYS.map((key) => {
        const name = text(accessibleNameRecord[key], `instances.${id}.expectedAccessibleNames.${key}`, true);
        if (name) assertAccessibleTargetSafe(name);
        return [key, name];
      }),
    ) as unknown as ExpectedAccessibleNamesConfig;
    for (const key of ACTION_KEYS) {
      if (Boolean(selectors[key]) !== Boolean(expectedAccessibleNames[key])) {
        throw new Error(`instances.${id}: ${key} exige seletor e nome acessível esperado em conjunto`);
      }
    }
    return {
      id,
      enabled: bool(item.enabled, `instances.${id}.enabled`),
      accountLabel: text(item.accountLabel, `instances.${id}.accountLabel`),
      environment: text(item.environment, `instances.${id}.environment`),
      helpers: {
        autoPotion: bool(helpers.autoPotion, `instances.${id}.helpers.autoPotion`),
        autoRevive: bool(helpers.autoRevive, `instances.${id}.helpers.autoRevive`),
      },
      selectors,
      expectedAccessibleNames,
    } satisfies InstanceConfig;
  });

  const level = text(logging.level, "logging.level");
  if (!["debug", "info", "warn", "error"].includes(level)) throw new Error("logging.level inválido");
  return {
    schemaVersion: 1,
    game: {
      name: "Poke Idle World",
      url: "https://poke.idleworld.online",
      playUrl: "https://poke.idleworld.online/play",
      rulesAcknowledged: bool(game.rulesAcknowledged, "game.rulesAcknowledged"),
    },
    runtime: { executionMode: "persistent_headless", dataDir: text(runtime.dataDir, "runtime.dataDir") },
    browser: {
      headless: true,
      maxPages: 1,
      viewport: { width: integer(viewport.width, "browser.viewport.width", 800, 1920), height: integer(viewport.height, "browser.viewport.height", 600, 1080) },
      resources: {
        blockMedia: bool(resources.blockMedia, "browser.resources.blockMedia"),
        blockedUrlPatterns,
      },
    },
    supervisor: {
      heartbeatSeconds: integer(supervisor.heartbeatSeconds, "supervisor.heartbeatSeconds", 5, 60),
      staleAfterSeconds: integer(supervisor.staleAfterSeconds, "supervisor.staleAfterSeconds", 15, 300),
      maxRestarts: integer(supervisor.maxRestarts, "supervisor.maxRestarts", 1, 20),
      restartWindowMinutes: integer(supervisor.restartWindowMinutes, "supervisor.restartWindowMinutes", 5, 240),
      circuitFailures: integer(supervisor.circuitFailures, "supervisor.circuitFailures", 2, 20),
      circuitWindowMinutes: integer(supervisor.circuitWindowMinutes, "supervisor.circuitWindowMinutes", 5, 240),
      circuitCooldownMinutes: integer(supervisor.circuitCooldownMinutes, "supervisor.circuitCooldownMinutes", 5, 1440),
      backoffBaseSeconds: integer(supervisor.backoffBaseSeconds, "supervisor.backoffBaseSeconds", 1, 60),
      backoffMaxSeconds: integer(supervisor.backoffMaxSeconds, "supervisor.backoffMaxSeconds", 30, 3600),
    },
    dashboard: { host: text(dashboard.host, "dashboard.host"), port: integer(dashboard.port, "dashboard.port", 1024, 65535) },
    logging: {
      level: level as AppConfig["logging"]["level"],
      rotateMegabytes: numberInRange(logging.rotateMegabytes, "logging.rotateMegabytes", 0.1, 100),
      retainFiles: integer(logging.retainFiles, "logging.retainFiles", 2, 50),
    },
    metrics: {
      sampleSeconds: integer(metrics.sampleSeconds, "metrics.sampleSeconds", 10, 600),
      historySamples: integer(metrics.historySamples, "metrics.historySamples", 10, 20_000),
    },
    instances,
  };
}

export function resolveDataDir(config: AppConfig): string {
  return resolve(config.runtime.dataDir);
}

export function instanceProfileDir(config: AppConfig, instanceId: string): string {
  return resolve(resolveDataDir(config), "profile", instanceId);
}

export function contractIsComplete(instance: InstanceConfig): boolean {
  const required: Array<keyof SelectorsConfig> = ["gameReady", "loginRequired", "characterRoot", "characterFainted", "characterHp", "huntActive", "suppliesMissing"];
  const helpersComplete =
    (!instance.helpers.autoPotion || Boolean(instance.selectors.autoPotionToggle && instance.selectors.autoPotionEnabled && instance.expectedAccessibleNames.autoPotionToggle)) &&
    (!instance.helpers.autoRevive || Boolean(instance.selectors.autoReviveToggle && instance.selectors.autoReviveEnabled && instance.expectedAccessibleNames.autoReviveToggle));
  const huntActionComplete = Boolean(
    (instance.selectors.huntStart && instance.expectedAccessibleNames.huntStart) ||
    (instance.selectors.huntResume && instance.expectedAccessibleNames.huntResume),
  );
  return required.every((key) => instance.selectors[key].length > 0) &&
    huntActionComplete && helpersComplete;
}

function record(value: unknown, path: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${path} deve ser um objeto`);
  return value as Record<string, unknown>;
}
function exactKeys(value: Record<string, unknown>, allowed: readonly string[], path: string): void {
  const unknown = Object.keys(value).filter((key) => !allowed.includes(key));
  const missing = allowed.filter((key) => !(key in value));
  if (unknown.length || missing.length) throw new Error(`${path}: chaves inválidas (desconhecidas=${unknown.join(",")}; ausentes=${missing.join(",")})`);
}
function literal<T extends string | number | boolean>(value: unknown, expected: T, path: string): asserts value is T {
  if (value !== expected) throw new Error(`${path} deve ser ${String(expected)}`);
}
function text(value: unknown, path: string, allowEmpty = false): string {
  if (typeof value !== "string" || (!allowEmpty && value.trim().length === 0)) throw new Error(`${path} deve ser texto${allowEmpty ? "" : " não vazio"}`);
  return value.trim();
}
function bool(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${path} deve ser booleano`);
  return value;
}
function integer(value: unknown, path: string, min: number, max: number): number {
  const result = numberInRange(value, path, min, max);
  if (!Number.isInteger(result)) throw new Error(`${path} deve ser inteiro`);
  return result;
}
function numberInRange(value: unknown, path: string, min: number, max: number): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) throw new Error(`${path} deve estar entre ${min} e ${max}`);
  return value;
}
function textArray(value: unknown, path: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || item.length === 0)) throw new Error(`${path} deve ser uma lista de textos`);
  return [...value];
}
