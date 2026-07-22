import { appendFile, mkdir, rename, stat, unlink } from "node:fs/promises";
import { dirname } from "node:path";
import { redact, sanitizeErrorMessage } from "./security.js";

type LogLevel = "debug" | "info" | "warn" | "error";

const LEVEL_WEIGHT: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 };

export class SafeLogger {
  readonly #path: string;
  readonly #level: LogLevel;
  readonly #maxBytes: number;
  readonly #retainFiles: number;
  #queue: Promise<void> = Promise.resolve();

  constructor(path: string, level: LogLevel, rotateMegabytes: number, retainFiles: number) {
    this.#path = path;
    this.#level = level;
    this.#maxBytes = rotateMegabytes * 1024 * 1024;
    this.#retainFiles = retainFiles;
  }

  debug(event: string, data: Record<string, unknown> = {}): void {
    this.#write("debug", event, data);
  }

  info(event: string, data: Record<string, unknown> = {}): void {
    this.#write("info", event, data);
  }

  warn(event: string, data: Record<string, unknown> = {}): void {
    this.#write("warn", event, data);
  }

  error(event: string, data: Record<string, unknown> = {}): void {
    this.#write("error", event, data);
  }

  async flush(): Promise<void> {
    await this.#queue;
  }

  #write(level: LogLevel, event: string, data: Record<string, unknown>): void {
    if (LEVEL_WEIGHT[level] < LEVEL_WEIGHT[this.#level]) return;
    const entry = JSON.stringify(
      redact({ timestamp: new Date().toISOString(), level, event, ...data }),
    );
    this.#queue = this.#queue
      .then(async () => {
        await mkdir(dirname(this.#path), { recursive: true, mode: 0o700 });
        await this.#rotateIfNeeded();
        await appendFile(this.#path, `${entry}\n`, { encoding: "utf8", mode: 0o600 });
      })
      .catch((error: unknown) => {
        const fallback = JSON.stringify({
          timestamp: new Date().toISOString(),
          level: "error",
          event: "log_write_failed",
          message: sanitizeErrorMessage(error),
        });
        process.stderr.write(`${fallback}\n`);
      });
  }

  async #rotateIfNeeded(): Promise<void> {
    const current = await stat(this.#path).catch(() => null);
    if (!current || current.size < this.#maxBytes) return;
    await unlink(`${this.#path}.${this.#retainFiles}`).catch(() => undefined);
    for (let index = this.#retainFiles - 1; index >= 1; index -= 1) {
      await rename(`${this.#path}.${index}`, `${this.#path}.${index + 1}`).catch(() => undefined);
    }
    await rename(this.#path, `${this.#path}.1`);
  }
}
