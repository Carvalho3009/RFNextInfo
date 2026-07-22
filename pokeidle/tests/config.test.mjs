import assert from "node:assert/strict";
import { test } from "node:test";
import { contractIsComplete, validateConfig } from "../dist/server/config.js";

function validConfig() {
  return {
    schemaVersion: 1,
    game: { name: "Poke Idle World", url: "https://poke.idleworld.online", playUrl: "https://poke.idleworld.online/play", rulesAcknowledged: false },
    runtime: { executionMode: "persistent_headless", dataDir: "data" },
    browser: { headless: true, maxPages: 1, viewport: { width: 1024, height: 720 }, resources: { blockMedia: false, blockedUrlPatterns: [] } },
    supervisor: { heartbeatSeconds: 15, staleAfterSeconds: 45, maxRestarts: 5, restartWindowMinutes: 30, circuitFailures: 5, circuitWindowMinutes: 15, circuitCooldownMinutes: 30, backoffBaseSeconds: 5, backoffMaxSeconds: 300 },
    dashboard: { host: "127.0.0.1", port: 8787 },
    logging: { level: "info", rotateMegabytes: 10, retainFiles: 10 },
    metrics: { sampleSeconds: 30, historySamples: 100 },
    instances: [{ id: "principal", enabled: false, accountLabel: "conta•••", environment: "local", helpers: { autoPotion: true, autoRevive: true }, selectors: {
      gameReady: "#ready", loginRequired: "#login", characterRoot: "#character", characterFainted: "#fainted", characterHp: "#hp", huntActive: "#hunt", huntStart: "#start", huntResume: "", suppliesMissing: "#supplies", autoPotionToggle: "#potion-toggle", autoPotionEnabled: "#potion-on", autoReviveToggle: "#revive-toggle", autoReviveEnabled: "#revive-on",
    }, expectedAccessibleNames: {
      huntStart: "Iniciar hunt", huntResume: "", autoPotionToggle: "Auto-Potion", autoReviveToggle: "Auto-Revive",
    }}],
  };
}

test("configuração estrita aceita contrato explícito", () => {
  const config = validateConfig(validConfig());
  assert.equal(contractIsComplete(config.instances[0]), true);
});

test("configuração recusa chaves desconhecidas e invariantes alteradas", () => {
  assert.throws(() => validateConfig({ ...validConfig(), sleepMode: true }));
  assert.throws(() => validateConfig({ ...validConfig(), browser: { ...validConfig().browser, headless: false } }));
  const unsafe = validConfig();
  unsafe.instances[0].selectors.huntStart = "#zzz";
  assert.throws(() => validateConfig(unsafe));
  const positional = validConfig();
  positional.instances[0].selectors.huntStart = "button:nth-child(2)";
  assert.throws(() => validateConfig(positional));
  const missingFingerprint = validConfig();
  missingFingerprint.instances[0].expectedAccessibleNames.huntStart = "";
  assert.throws(() => validateConfig(missingFingerprint));
});

test("helpers habilitados exigem estado, alvo e identidade positiva", () => {
  const missingState = validConfig();
  missingState.instances[0].selectors.autoPotionEnabled = "";
  assert.equal(contractIsComplete(validateConfig(missingState).instances[0]), false);
});
