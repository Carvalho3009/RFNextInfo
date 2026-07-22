import assert from "node:assert/strict";
import { readFile, rm } from "node:fs/promises";
import { test } from "node:test";
import { join } from "node:path";
import { assertAccessibleTargetMatches, assertAccessibleTargetSafe, assertDashboardTokenStrong, assertSelectorPolicy, redact, sanitizeErrorMessage, sanitizeUrl, tokensMatch } from "../dist/server/security.js";
import { SafeLogger } from "../dist/server/logger.js";

test("a política recusa alvos de sono, gasto, chat e PvP", () => {
  for (const value of ["Zzz", "SleepMode", "Modo Soneca", "Modo Sono", "offline", "💤", "Diamond shop", "Diamantes", "Comprar 500 gold", "2💎", "VIP boost", "chat", "PvP"]) {
    assert.throws(() => assertAccessibleTargetSafe(value));
  }
  assert.throws(() => assertAccessibleTargetSafe(""));
  assert.doesNotThrow(() => assertAccessibleTargetSafe("Auto-Potion"));
  assert.doesNotThrow(() => assertAccessibleTargetSafe("Retomar hunt"));
  assert.doesNotThrow(() => assertAccessibleTargetMatches(" Retomar   hunt ", "retomar hunt"));
  assert.throws(() => assertAccessibleTargetMatches("Iniciar hunt", "Retomar hunt"));
});

test("seletores perigosos são recusados antes de abrir o navegador", () => {
  assert.throws(() => assertSelectorPolicy("button.zzz-mode"));
  assert.throws(() => assertSelectorPolicy("#diamond-shop"));
  assert.doesNotThrow(() => assertSelectorPolicy('[data-testid="hunt-resume"]'));
  assert.throws(() => assertSelectorPolicy("button:nth-child(2)"));
  assert.throws(() => assertSelectorPolicy("button.primary"));
});

test("redação remove segredos e query strings", () => {
  const output = redact({ password: "canary-password", nested: { authorization: "Bearer canary" }, url: "https://example.test/path?token=canary#hash" });
  assert.deepEqual(output, { password: "[REDACTED]", nested: { authorization: "[REDACTED]" }, url: "https://example.test/path" });
  assert.equal(sanitizeUrl("wss://example.test/socket?token=secret"), "wss://example.test/socket");
  assert.equal(tokensMatch("abc", "abc"), true);
  assert.equal(tokensMatch("abc", "abd"), false);
  const embedded = sanitizeErrorMessage(new Error("goto https://example.test/path?token=canary token=canary Authorization: Bearer abc.def"));
  assert.equal(embedded.includes("canary"), false);
  assert.equal(embedded.includes("abc.def"), false);
  assert.throws(() => assertDashboardTokenStrong("short"));
  assert.doesNotThrow(() => assertDashboardTokenStrong("x".repeat(32)));
});

test("logger estruturado não persiste canário sensível", async () => {
  const path = join("data", "test", "security-log.ndjson");
  await rm(path, { force: true });
  const logger = new SafeLogger(path, "debug", 1, 2);
  logger.info("canary", { password: "DO-NOT-LOG", cookie: "DO-NOT-LOG", safe: "ok" });
  await logger.flush();
  const content = await readFile(path, "utf8");
  assert.equal(content.includes("DO-NOT-LOG"), false);
  assert.equal(content.includes("[REDACTED]"), true);
});
