import { resolve, join } from "node:path";
import { createDashboardServer } from "./api.js";
import { loadConfig, resolveDataDir } from "./config.js";
import { ProcessLock } from "./lock.js";
import { SafeLogger } from "./logger.js";
import { assertDashboardTokenStrong, sanitizeErrorMessage } from "./security.js";
import { SupervisorRegistry } from "./supervisor.js";

const configPath = resolve(process.env.POKEIDLE_CONFIG ?? "config.yaml");
const config = await loadConfig(configPath);
assertDashboardTokenStrong(process.env.POKEIDLE_DASHBOARD_TOKEN);

const dataDir = resolveDataDir(config);
const logger = new SafeLogger(
  join(dataDir, "logs", "supervisor.ndjson"),
  (process.env.POKEIDLE_LOG_LEVEL as "debug" | "info" | "warn" | "error" | undefined) ?? config.logging.level,
  config.logging.rotateMegabytes,
  config.logging.retainFiles,
);
const lock = new ProcessLock(join(dataDir, "locks", "supervisor.lock"), "supervisor");
await lock.acquire();

const registry = new SupervisorRegistry(config, configPath, logger);
const server = createDashboardServer(config, registry, logger);
server.listen(config.dashboard.port, config.dashboard.host, () => {
  logger.info("supervisor_listening", { host: config.dashboard.host, port: config.dashboard.port });
});
await registry.startEnabled(config);

let shuttingDown = false;
async function shutdown(signal: string): Promise<void> {
  if (shuttingDown) return;
  shuttingDown = true;
  logger.info("supervisor_shutdown", { signal });
  await registry.shutdown();
  await new Promise<void>((resolveClose) => server.close(() => resolveClose()));
  await lock.release();
  await logger.flush();
}

process.on("SIGINT", () => void shutdown("SIGINT"));
process.on("SIGTERM", () => void shutdown("SIGTERM"));
process.on("uncaughtException", (error) => {
  logger.error("uncaught_exception", { message: sanitizeErrorMessage(error) });
  void shutdown("uncaughtException").finally(() => {
    process.exitCode = 1;
  });
});
process.on("unhandledRejection", (error) => {
  logger.error("unhandled_rejection", { message: sanitizeErrorMessage(error) });
  void shutdown("unhandledRejection").finally(() => {
    process.exitCode = 1;
  });
});
