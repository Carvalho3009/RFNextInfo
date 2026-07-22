import assert from "node:assert/strict";
import { test } from "node:test";
import { decideNextState } from "../dist/server/state-machine.js";
import { BoundedActionGate, ExponentialBackoff, FailureWindow } from "../dist/server/recovery.js";

const healthy = {
  contractComplete: true, gameReady: true, loginRequired: false, characterPresent: true,
  characterFainted: false, hpPercent: 82, huntActive: true, suppliesMissing: false,
  autoPotionEnabled: true, autoReviveEnabled: true, connected: true,
};
const context = (observation = healthy, extra = {}) => ({
  rulesAcknowledged: true, contractComplete: true, observation, nativeHelpersConfigured: true,
  recoveryAttempts: 0, maxRecoveryAttempts: 3, ...extra,
});

test("fluxo saudável chega a MONITOR_COMBAT", () => {
  let state = "BOOT";
  for (let index = 0; index < 10 && state !== "MONITOR_COMBAT"; index += 1) {
    state = decideNextState(state, context()).state;
  }
  assert.equal(state, "MONITOR_COMBAT");
});

test("login expirado exige parada segura, sem senha", () => {
  const expired = { ...healthy, loginRequired: true, gameReady: false };
  assert.equal(decideNextState("MONITOR_COMBAT", context(expired)).state, "SESSION_EXPIRED");
  assert.equal(decideNextState("SESSION_EXPIRED", context(expired)).state, "SAFE_STOP");
});

test("desconexão e reconexão voltam por AUTH_CHECK", () => {
  const offline = { ...healthy, connected: false };
  assert.equal(decideNextState("MONITOR_COMBAT", context(offline)).state, "RECOVER_CONNECTION");
  assert.equal(decideNextState("RECOVER_CONNECTION", context(healthy)).state, "AUTH_CHECK");
});

test("derrota, retorno e falta de suprimentos seguem caminhos conservadores", () => {
  const fainted = { ...healthy, characterFainted: true };
  assert.equal(decideNextState("MONITOR_COMBAT", context(fainted)).state, "RECOVER_FROM_FAINT");
  assert.equal(decideNextState("RECOVER_FROM_FAINT", context(healthy)).state, "VERIFY_CHARACTER");
  assert.equal(decideNextState("RECOVER_FROM_FAINT", context(fainted, { recoveryAttempts: 3 })).state, "SAFE_STOP");
  assert.equal(decideNextState("MONITOR_COMBAT", context({ ...healthy, huntActive: false })).state, "VERIFY_HUNT");
  assert.equal(decideNextState("MONITOR_COMBAT", context({ ...healthy, suppliesMissing: true })).state, "SAFE_STOP");
});

test("regra não confirmada ou DOM alterado bloqueia produção", () => {
  assert.equal(decideNextState("BOOT", context(healthy, { rulesAcknowledged: false })).state, "SAFE_STOP");
  assert.equal(decideNextState("MONITOR_COMBAT", context(healthy, { contractComplete: false })).state, "SAFE_STOP");
});

test("backoff tem teto e circuit breaker abre no limite", () => {
  const backoff = new ExponentialBackoff(5, 30);
  assert.deepEqual([backoff.nextDelay(() => 0.5), backoff.nextDelay(() => 0.5), backoff.nextDelay(() => 0.5), backoff.nextDelay(() => 0.5)], [2500, 5000, 10000, 15000]);
  const breaker = new FailureWindow(3, 15, 30);
  assert.equal(breaker.recordFailure(1000), false);
  assert.equal(breaker.recordFailure(2000), false);
  assert.equal(breaker.recordFailure(3000), true);
  assert.equal(breaker.isOpen(4000), true);
});

test("ações online têm cooldown e orçamento finito", () => {
  const gate = new BoundedActionGate(2, 10_000);
  assert.equal(gate.attempt(1_000).allowed, true);
  const wait = gate.attempt(2_000);
  assert.equal(wait.allowed, false);
  assert.equal(wait.exhausted, false);
  assert.equal(wait.waitMs, 9_000);
  assert.equal(gate.attempt(11_000).allowed, true);
  assert.equal(gate.attempt(21_000).exhausted, true);
});

test("helper nativo desconfirmado retorna à configuração", () => {
  assert.equal(decideNextState("MONITOR_COMBAT", context(healthy, { nativeHelpersConfigured: false })).state, "CONFIGURE_NATIVE_HELPERS");
});
