import { fork, type ChildProcess } from "node:child_process";
import { fileURLToPath } from "node:url";
import type { AppConfig, InstanceConfig } from "./config.js";
import { ExponentialBackoff, FailureWindow } from "./recovery.js";
import type { SafeLogger } from "./logger.js";
import { sanitizeErrorMessage } from "./security.js";
import {
  toneForState,
  type ControllerToWorkerMessage,
  type InstanceStatus,
  type WorkerToControllerMessage,
} from "./types.js";

type UpdateListener = (statuses: InstanceStatus[]) => void;

export class InstanceSupervisor {
  readonly #config: AppConfig;
  readonly #instance: InstanceConfig;
  readonly #configPath: string;
  readonly #logger: SafeLogger;
  readonly #onUpdate: () => void;
  readonly #backoff: ExponentialBackoff;
  readonly #breaker: FailureWindow;
  #child: ChildProcess | null = null;
  #restartTimestamps: number[] = [];
  #restartTimer: NodeJS.Timeout | null = null;
  #manualStop = false;
  #watchdogInitiated = false;
  #status: InstanceStatus;

  constructor(
    config: AppConfig,
    instance: InstanceConfig,
    configPath: string,
    logger: SafeLogger,
    onUpdate: () => void,
  ) {
    this.#config = config;
    this.#instance = instance;
    this.#configPath = configPath;
    this.#logger = logger;
    this.#onUpdate = onUpdate;
    this.#backoff = new ExponentialBackoff(config.supervisor.backoffBaseSeconds, config.supervisor.backoffMaxSeconds);
    this.#breaker = new FailureWindow(
      config.supervisor.circuitFailures,
      config.supervisor.circuitWindowMinutes,
      config.supervisor.circuitCooldownMinutes,
    );
    this.#status = emptyStatus(instance);
  }

  status(): InstanceStatus {
    return { ...this.#status, metrics: [...this.#status.metrics] };
  }

  async start(operatorInitiated = false): Promise<void> {
    if (this.#child) return;
    if (operatorInitiated) {
      this.#breaker.reset();
      this.#backoff.reset();
      this.#restartTimestamps = [];
    } else if (this.#breaker.isOpen()) {
      this.#setCircuitStatus();
      return;
    }
    this.#manualStop = false;
    const workerPath = fileURLToPath(new URL("./worker.js", import.meta.url));
    const child = fork(workerPath, ["--instance", this.#instance.id], {
      env: childEnvironment(this.#configPath),
      stdio: ["ignore", "ignore", "ignore", "ipc"],
      windowsHide: true,
    });
    this.#child = child;
    this.#status = {
      ...this.#status,
      running: true,
      pid: child.pid ?? null,
      startedAt: new Date().toISOString(),
      lastHeartbeat: new Date().toISOString(),
      state: "BOOT",
      tone: "attention",
      reason: null,
    };
    this.#logger.info("instance_spawned", { instanceId: this.#instance.id, pid: child.pid });
    child.on("message", (message: WorkerToControllerMessage) => this.#handleMessage(message));
    child.on("exit", (code, signal) => this.#handleExit(code, signal));
    child.on("error", (error) => this.#logger.error("worker_process_error", { instanceId: this.#instance.id, message: sanitizeErrorMessage(error) }));
    this.#onUpdate();
  }

  async stop(reason = "Parada solicitada pelo operador"): Promise<void> {
    this.#manualStop = true;
    if (this.#restartTimer) clearTimeout(this.#restartTimer);
    this.#restartTimer = null;
    const child = this.#child;
    if (!child) {
      this.#status = { ...this.#status, running: false, state: "SAFE_STOP", tone: "stopped", reason };
      this.#onUpdate();
      return;
    }
    child.send({ type: "stop", reason } satisfies ControllerToWorkerMessage);
    await new Promise<void>((resolveStop) => {
      const timeout = setTimeout(() => {
        child.kill("SIGKILL");
        resolveStop();
      }, 10_000);
      child.once("exit", () => {
        clearTimeout(timeout);
        resolveStop();
      });
    });
  }

  async restart(): Promise<void> {
    await this.stop("Reinício solicitado pelo operador");
    await this.start(true);
  }

  checkHeartbeat(now = Date.now()): void {
    if (!this.#child || !this.#status.lastHeartbeat) return;
    const elapsed = now - Date.parse(this.#status.lastHeartbeat);
    if (elapsed > this.#config.supervisor.staleAfterSeconds * 1000) {
      this.#logger.error("worker_heartbeat_stale", { instanceId: this.#instance.id, elapsedMs: elapsed });
      this.#watchdogInitiated = true;
      this.#child.kill("SIGTERM");
    }
  }

  #handleMessage(message: WorkerToControllerMessage): void {
    if (message.type === "status") {
      this.#status = {
        ...message.status,
        restartCount: this.#restartTimestamps.length,
        circuitOpenUntil: this.#breaker.openUntil(),
      };
    } else if (message.type === "heartbeat") {
      this.#status = { ...this.#status, lastHeartbeat: message.at };
    } else if (message.type === "fatal") {
      this.#status = { ...this.#status, reason: message.reason, tone: "error" };
    }
    this.#onUpdate();
  }

  #handleExit(code: number | null, signal: NodeJS.Signals | null): void {
    const watchdogInitiated = this.#watchdogInitiated;
    this.#watchdogInitiated = false;
    this.#child = null;
    this.#status = { ...this.#status, running: false, pid: null };
    this.#logger.warn("worker_exited", { instanceId: this.#instance.id, code, signal, manual: this.#manualStop });
    this.#onUpdate();
    if (this.#manualStop || (code === 0 && !watchdogInitiated)) return;
    const now = Date.now();
    const windowMs = this.#config.supervisor.restartWindowMinutes * 60_000;
    this.#restartTimestamps = this.#restartTimestamps.filter((timestamp) => timestamp >= now - windowMs);
    this.#restartTimestamps.push(now);
    const overRestartBudget = this.#restartTimestamps.length >= this.#config.supervisor.maxRestarts;
    const circuitOpen = this.#breaker.recordFailure(now);
    if (overRestartBudget || circuitOpen) {
      this.#setCircuitStatus();
      return;
    }
    this.#restartTimer = setTimeout(() => void this.start(), this.#backoff.nextDelay());
  }

  #setCircuitStatus(): void {
    this.#status = {
      ...this.#status,
      running: false,
      state: "ERROR_BACKOFF",
      tone: toneForState("ERROR_BACKOFF"),
      reason: "Circuit breaker aberto após falhas repetidas",
      circuitOpenUntil: this.#breaker.openUntil(),
    };
    this.#onUpdate();
  }
}

export class SupervisorRegistry {
  readonly #supervisors = new Map<string, InstanceSupervisor>();
  readonly #listeners = new Set<UpdateListener>();
  readonly #watchdog: NodeJS.Timeout;

  constructor(config: AppConfig, configPath: string, logger: SafeLogger) {
    const update = (): void => this.#emit();
    for (const instance of config.instances) {
      this.#supervisors.set(instance.id, new InstanceSupervisor(config, instance, configPath, logger, update));
    }
    this.#watchdog = setInterval(() => {
      for (const supervisor of this.#supervisors.values()) supervisor.checkHeartbeat();
    }, 5_000);
  }

  statuses(): InstanceStatus[] {
    return [...this.#supervisors.values()].map((supervisor) => supervisor.status());
  }

  subscribe(listener: UpdateListener): () => void {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  }

  async startEnabled(config: AppConfig): Promise<void> {
    const enabled = config.instances.filter((instance) => instance.enabled);
    for (const [index, instance] of enabled.entries()) {
      if (index > 0) await delay(1_500);
      await this.start(instance.id);
    }
  }

  async start(id: string): Promise<void> {
    await this.#get(id).start(true);
  }

  async stop(id: string): Promise<void> {
    await this.#get(id).stop();
  }

  async restart(id: string): Promise<void> {
    await this.#get(id).restart();
  }

  async shutdown(): Promise<void> {
    clearInterval(this.#watchdog);
    await Promise.all([...this.#supervisors.values()].map((supervisor) => supervisor.stop("Supervisor encerrado")));
  }

  #get(id: string): InstanceSupervisor {
    const supervisor = this.#supervisors.get(id);
    if (!supervisor) throw new Error(`Instância desconhecida: ${id}`);
    return supervisor;
  }

  #emit(): void {
    const snapshot = this.statuses();
    for (const listener of this.#listeners) listener(snapshot);
  }
}

function childEnvironment(configPath: string): NodeJS.ProcessEnv {
  const output: NodeJS.ProcessEnv = {};
  const sensitiveName = /password|passwd|authorization|cookie|token|secret|storage|session|credential|api[_-]?key/i;
  for (const [key, value] of Object.entries(process.env)) {
    if (!sensitiveName.test(key)) output[key] = value;
  }
  output.POKEIDLE_CONFIG = configPath;
  return output;
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));
}

function emptyStatus(instance: InstanceConfig): InstanceStatus {
  return {
    id: instance.id,
    accountLabel: instance.accountLabel,
    environment: instance.environment,
    state: "SAFE_STOP",
    tone: "stopped",
    running: false,
    pid: null,
    startedAt: null,
    lastHeartbeat: null,
    reason: "Instância não iniciada",
    restartCount: 0,
    circuitOpenUntil: null,
    observation: null,
    latestMetric: null,
    metrics: [],
  };
}
