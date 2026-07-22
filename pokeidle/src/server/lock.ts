import { open, readFile, rm } from "node:fs/promises";
import { dirname } from "node:path";
import { mkdir } from "node:fs/promises";

interface LockPayload {
  pid: number;
  startedAt: string;
  owner: string;
}

function processExists(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

export class ProcessLock {
  readonly #path: string;
  readonly #owner: string;
  #acquired = false;

  constructor(path: string, owner: string) {
    this.#path = path;
    this.#owner = owner;
  }

  async acquire(): Promise<void> {
    await mkdir(dirname(this.#path), { recursive: true, mode: 0o700 });
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const handle = await open(this.#path, "wx", 0o600);
        const payload: LockPayload = {
          pid: process.pid,
          startedAt: new Date().toISOString(),
          owner: this.#owner,
        };
        await handle.writeFile(JSON.stringify(payload), "utf8");
        await handle.close();
        this.#acquired = true;
        return;
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
        const existing = await this.#readExisting();
        if (existing && processExists(existing.pid)) {
          throw new Error(`Lock ativo para ${existing.owner} (PID ${existing.pid})`);
        }
        if (attempt === 0) {
          await rm(this.#path, { force: true });
          continue;
        }
      }
    }
    throw new Error(`Não foi possível adquirir lock ${this.#owner}`);
  }

  async release(): Promise<void> {
    if (!this.#acquired) return;
    const existing = await this.#readExisting();
    if (existing?.pid === process.pid) await rm(this.#path, { force: true });
    this.#acquired = false;
  }

  async #readExisting(): Promise<LockPayload | null> {
    try {
      return JSON.parse(await readFile(this.#path, "utf8")) as LockPayload;
    } catch {
      return null;
    }
  }
}
