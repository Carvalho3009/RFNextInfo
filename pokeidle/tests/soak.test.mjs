import assert from "node:assert/strict";
import { test } from "node:test";
import { decideNextState } from "../dist/server/state-machine.js";

test("soak simulado mantém estado estável por 250 mil ciclos", () => {
  const observation = { contractComplete: true, gameReady: true, loginRequired: false, characterPresent: true, characterFainted: false, hpPercent: 50, huntActive: true, suppliesMissing: false, autoPotionEnabled: true, autoReviveEnabled: true, connected: true };
  const context = { rulesAcknowledged: true, contractComplete: true, observation, nativeHelpersConfigured: true, recoveryAttempts: 0, maxRecoveryAttempts: 3 };
  const before = process.memoryUsage().heapUsed;
  let state = "MONITOR_COMBAT";
  for (let index = 0; index < 250_000; index += 1) state = decideNextState(state, context).state;
  const growth = process.memoryUsage().heapUsed - before;
  assert.equal(state, "MONITOR_COMBAT");
  assert.ok(growth < 32 * 1024 * 1024, `crescimento inesperado: ${growth}`);
});
