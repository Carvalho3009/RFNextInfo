import { mkdir, readdir, rm } from "node:fs/promises";
import { join } from "node:path";
import { BrowserSession } from "./browser-session.js";
import { contractIsComplete, loadConfig, resolveDataDir } from "./config.js";
import { ProcessLock } from "./lock.js";
import { SafeLogger } from "./logger.js";
import { BoundedActionGate, ExponentialBackoff } from "./recovery.js";
import { sanitizeErrorMessage } from "./security.js";
import { decideNextState } from "./state-machine.js";
import {
  toneForState,
  type AutomationState,
  type ControllerToWorkerMessage,
  type GameObservation,
  type InstanceStatus,
  type WorkerToControllerMessage,
} from "./types.js";

const instanceId = argumentValue("--instance");
if (!instanceId) throw new Error("--instance é obrigatório");

const config = await loadConfig();
const instance = config.instances.find((candidate) => candidate.id === instanceId);
if (!instance) throw new Error(`Instância não encontrada: ${instanceId}`);

const dataDir = resolveDataDir(config);
const logger = new SafeLogger(
  join(dataDir, "logs", `${instance.id}.ndjson`),
  (process.env.POKEIDLE_LOG_LEVEL as "debug" | "info" | "warn" | "error" | undefined) ?? config.logging.level,
  config.logging.rotateMegabytes,
  config.logging.retainFiles,
);
const lock = new ProcessLock(join(dataDir, "locks", `${instance.id}.lock`), `instance:${instance.id}`);
const browser = new BrowserSession(config, instance, logger);
const backoff = new ExponentialBackoff(
  config.supervisor.backoffBaseSeconds,
  config.supervisor.backoffMaxSeconds,
);
const nativeHelperGate = new BoundedActionGate(1, 0);
const huntActionGate = new BoundedActionGate(3, 10_000);

let state: AutomationState = "BOOT";
let observation: GameObservation | null = null;
let running = true;
let nativeHelpersConfigured = false;
let recoveryAttempts = 0;
let loopTimer: NodeJS.Timeout | null = null;
let loopRunning = false;
let lastTickAt = 0;
let metricTimer: NodeJS.Timeout | null = null;
let heartbeatTimer: NodeJS.Timeout | null = null;
const metrics: InstanceStatus["metrics"] = [];
const startedAt = new Date().toISOString();
let reason: string | null = null;

function status(): InstanceStatus {
  return {
    id: instance.id,
    accountLabel: instance.accountLabel,
    environment: instance.environment,
    state,
    tone: toneForState(state),
    running,
    pid: process.pid,
    startedAt,
    lastHeartbeat: new Date().toISOString(),
    reason,
    restartCount: 0,
    circuitOpenUntil: null,
    observation,
    latestMetric: metrics.at(-1) ?? null,
    metrics: metrics.slice(-Math.min(config.metrics.historySamples, 180)),
  };
}

function send(message: WorkerToControllerMessage): void {
  if (process.send) process.send(message);
}

function publish(): void {
  send({ type: "status", status: status() });
}

function schedule(delayMs: number): void {
  if (!running || state === "SAFE_STOP") return;
  if (loopTimer) clearTimeout(loopTimer);
  const monitorFloor = state === "MONITOR_COMBAT" ? Math.max(0, 5_000 - (Date.now() - lastTickAt)) : 0;
  loopTimer = setTimeout(() => void tick(), Math.max(delayMs, monitorFloor));
}

async function tick(): Promise<void> {
  if (!running || loopRunning || state === "SAFE_STOP") return;
  loopRunning = true;
  lastTickAt = Date.now();
  let nextDelayOverride: number | null = null;
  try {
    if (state !== "BOOT") {
      observation = await browser.observe();
      assertObservationUnambiguous(observation);
    }
    if (state === "MONITOR_COMBAT" && observation && (
      (instance.helpers.autoPotion && observation.autoPotionEnabled !== true) ||
      (instance.helpers.autoRevive && observation.autoReviveEnabled !== true)
    )) {
      nativeHelpersConfigured = false;
    }
    if (state === "CONFIGURE_NATIVE_HELPERS" && !nativeHelpersConfigured) {
      const attempt = nativeHelperGate.attempt();
      if (attempt.exhausted) throw new Error("POLICY_BLOCK: helper nativo não confirmou após uma única ação");
      if (attempt.allowed) {
        nativeHelpersConfigured = await browser.configureNativeHelpers();
        observation = await browser.observe();
        assertObservationUnambiguous(observation);
      } else {
        nextDelayOverride = attempt.waitMs;
      }
    } else if (state === "START_OR_RESUME_HUNT" && observation?.huntActive !== true) {
      const attempt = huntActionGate.attempt();
      if (attempt.exhausted) throw new Error("POLICY_BLOCK: hunt não confirmou após três tentativas limitadas");
      if (attempt.allowed) {
        await browser.startOrResumeHunt();
        await delay(1_000);
        observation = await browser.observe();
        assertObservationUnambiguous(observation);
      } else {
        nextDelayOverride = attempt.waitMs;
      }
    } else if (state === "RECOVER_FROM_FAINT") {
      recoveryAttempts += 1;
      nextDelayOverride = 10_000;
    } else if (state === "RECOVER_CONNECTION") {
      recoveryAttempts += 1;
      await browser.recoverConnection();
      observation = await browser.observe();
      assertObservationUnambiguous(observation);
    } else if (state === "RECOVER_FROM_FAINT") {
      recoveryAttempts += 1;
      nextDelayOverride = 10_000;
    }

    const decision = decideNextState(state, {
      rulesAcknowledged: config.game.rulesAcknowledged,
      contractComplete: contractIsComplete(instance),
      observation,
      nativeHelpersConfigured,
      recoveryAttempts,
      maxRecoveryAttempts: 3,
    });
    const previous = state;
    state = decision.state;
    reason = decision.reason;
    if (previous !== state) logger.info("state_transition", { instanceId, from: previous, to: state, reason });
    if (previous !== "CONFIGURE_NATIVE_HELPERS" && state === "CONFIGURE_NATIVE_HELPERS") nativeHelperGate.reset();
    if (previous !== "START_OR_RESUME_HUNT" && state === "START_OR_RESUME_HUNT") huntActionGate.reset();
    if (previous !== "RECOVER_FROM_FAINT" && state === "RECOVER_FROM_FAINT") recoveryAttempts = 0;
    if (state === "MONITOR_COMBAT") {
      backoff.reset();
      recoveryAttempts = 0;
      nativeHelperGate.reset();
      huntActionGate.reset();
    }
    publish();
    if (state === "SAFE_STOP") {
      await browser.close();
      return;
    }
    if (state === "ERROR_BACKOFF") schedule(backoff.nextDelay());
    else schedule(nextDelayOverride ?? (state === "MONITOR_COMBAT" ? 30_000 : 1_000));
  } catch (error) {
    const message = sanitizeErrorMessage(error);
    const policyFault = message.startsWith("POLICY_BLOCK") || message.includes("Contrato DOM");
    const screenshotAllowed = state === "MONITOR_COMBAT";
    reason = message;
    state = policyFault ? "SAFE_STOP" : "ERROR_BACKOFF";
    logger.error("worker_tick_failed", { instanceId, state, message });
    if (!policyFault) {
      const errorDir = join(dataDir, "errors", instance.id);
      await mkdir(errorDir, { recursive: true, mode: 0o700 });
      await browser.screenshotOnError(join(errorDir, `${Date.now()}.png`), screenshotAllowed);
      await pruneErrorScreenshots(errorDir, config.logging.retainFiles);
    }
    publish();
    if (state === "SAFE_STOP") {
      await browser.close();
    } else if (!browser.isOpen()) {
      send({ type: "fatal", reason: message });
      await shutdown(message, 1);
    } else {
      schedule(backoff.nextDelay());
    }
  } finally {
    loopRunning = false;
  }
}

async function shutdown(shutdownReason: string, exitCode = 0): Promise<void> {
  if (!running) return;
  running = false;
  reason = sanitizeErrorMessage(shutdownReason);
  state = "SAFE_STOP";
  if (loopTimer) clearTimeout(loopTimer);
  if (metricTimer) clearInterval(metricTimer);
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  await browser.close();
  await lock.release();
  publish();
  await logger.flush();
  process.exitCode = exitCode;
  if (process.connected) process.disconnect();
}

process.on("message", (message: ControllerToWorkerMessage) => {
  if (message.type === "stop") void shutdown(message.reason);
  if (message.type === "snapshot") publish();
});
process.on("SIGTERM", () => void shutdown("SIGTERM"));
process.on("SIGINT", () => void shutdown("SIGINT"));
process.on("uncaughtException", (error) => {
  const message = sanitizeErrorMessage(error);
  logger.error("uncaught_exception", { instanceId, message });
  send({ type: "fatal", reason: message });
  void shutdown("Exceção não tratada", 1);
});
process.on("unhandledRejection", (error) => {
  const message = sanitizeErrorMessage(error);
  logger.error("unhandled_rejection", { instanceId, message });
  send({ type: "fatal", reason: message });
  void shutdown(message, 1);
});

await lock.acquire();
logger.info("worker_started", { instanceId, profile: `data/profile/${instance.id}` });
send({ type: "ready", pid: process.pid });

if (!config.game.rulesAcknowledged || !contractIsComplete(instance)) {
  const decision = decideNextState("BOOT", {
    rulesAcknowledged: config.game.rulesAcknowledged,
    contractComplete: contractIsComplete(instance),
    observation: null,
    nativeHelpersConfigured: false,
    recoveryAttempts: 0,
    maxRecoveryAttempts: 3,
  });
  state = decision.state;
  reason = decision.reason;
  publish();
} else {
  await browser.launch(() => {
    if (state === "MONITOR_COMBAT") schedule(350);
  });
  schedule(0);
}

heartbeatTimer = setInterval(() => {
  send({ type: "heartbeat", at: new Date().toISOString() });
}, config.supervisor.heartbeatSeconds * 1000);

metricTimer = setInterval(() => {
  if (!browser.isOpen()) return;
  void browser.sampleMetrics().then((sample) => {
    metrics.push(sample);
    if (metrics.length > config.metrics.historySamples) metrics.splice(0, metrics.length - config.metrics.historySamples);
    publish();
  });
}, config.metrics.sampleSeconds * 1000);

function argumentValue(name: string): string | null {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] ?? null : null;
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));
}

function assertObservationUnambiguous(value: GameObservation): void {
  const required = [value.gameReady, value.loginRequired, value.characterPresent, value.characterFainted, value.huntActive, value.suppliesMissing];
  if (required.some((item) => item === null)) throw new Error("POLICY_BLOCK: contrato DOM ficou ambíguo");
  if (value.characterPresent === true && value.hpPercent === null) throw new Error("POLICY_BLOCK: HP não pôde ser validado");
}

async function pruneErrorScreenshots(directory: string, retain: number): Promise<void> {
  const names = (await readdir(directory).catch(() => []))
    .filter((name) => /^\d+\.png$/.test(name))
    .sort((left, right) => right.localeCompare(left));
  await Promise.all(names.slice(retain).map((name) => rm(join(directory, name), { force: true })));
}
