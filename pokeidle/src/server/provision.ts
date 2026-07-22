import { createInterface } from "node:readline/promises";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { stdin as input, stdout as output } from "node:process";
import { chromium } from "playwright";
import { instanceProfileDir, loadConfig, resolveDataDir } from "./config.js";
import { ProcessLock } from "./lock.js";

const instanceId = process.argv[2];
if (!instanceId) throw new Error("Uso: npm run provision -- <id-da-instancia>");
const config = await loadConfig();
const instance = config.instances.find((candidate) => candidate.id === instanceId);
if (!instance) throw new Error(`Instância desconhecida: ${instanceId}`);
const profileDir = instanceProfileDir(config, instance.id);
const lock = new ProcessLock(join(resolveDataDir(config), "locks", `${instance.id}.lock`), `provision:${instance.id}`);
await lock.acquire();
await mkdir(profileDir, { recursive: true, mode: 0o700 });

try {
  const context = await chromium.launchPersistentContext(profileDir, {
    headless: false,
    viewport: config.browser.viewport,
    args: ["--disable-extensions", "--no-first-run", "--no-default-browser-check"],
  });
  try {
    const page = context.pages()[0] ?? (await context.newPage());
    for (const extraPage of context.pages().slice(1)) await extraPage.close();
    await page.goto("https://poke.idleworld.online/login", { waitUntil: "domcontentloaded" });
    output.write("Faça login manualmente na janela isolada. Nenhuma credencial será lida ou registrada.\n");
    const readline = createInterface({ input, output });
    await readline.question("Quando a sessão estiver pronta, pressione Enter para fechar o Chromium isolado. ");
    readline.close();
  } finally {
    await context.close();
  }
} finally {
  await lock.release();
}
