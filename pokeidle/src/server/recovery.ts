export class ExponentialBackoff {
  readonly #baseMs: number;
  readonly #maxMs: number;
  #attempt = 0;

  constructor(baseSeconds: number, maxSeconds: number) {
    this.#baseMs = baseSeconds * 1000;
    this.#maxMs = maxSeconds * 1000;
  }

  nextDelay(random = Math.random): number {
    const ceiling = Math.min(this.#maxMs, this.#baseMs * 2 ** this.#attempt);
    this.#attempt += 1;
    return Math.floor(random() * ceiling);
  }

  reset(): void {
    this.#attempt = 0;
  }
}

export class FailureWindow {
  readonly #limit: number;
  readonly #windowMs: number;
  readonly #cooldownMs: number;
  #failures: number[] = [];
  #openUntil = 0;

  constructor(limit: number, windowMinutes: number, cooldownMinutes: number) {
    this.#limit = limit;
    this.#windowMs = windowMinutes * 60_000;
    this.#cooldownMs = cooldownMinutes * 60_000;
  }

  recordFailure(now = Date.now()): boolean {
    this.#failures = this.#failures.filter((timestamp) => timestamp >= now - this.#windowMs);
    this.#failures.push(now);
    if (this.#failures.length >= this.#limit) this.#openUntil = now + this.#cooldownMs;
    return this.isOpen(now);
  }

  isOpen(now = Date.now()): boolean {
    return now < this.#openUntil;
  }

  openUntil(): string | null {
    return this.#openUntil > Date.now() ? new Date(this.#openUntil).toISOString() : null;
  }

  reset(): void {
    this.#failures = [];
    this.#openUntil = 0;
  }
}

export type ActionAttemptDecision =
  | { allowed: true; waitMs: 0; exhausted: false }
  | { allowed: false; waitMs: number; exhausted: false }
  | { allowed: false; waitMs: 0; exhausted: true };

export class BoundedActionGate {
  readonly #maxAttempts: number;
  readonly #minimumIntervalMs: number;
  #attempts = 0;
  #lastAttemptAt = 0;

  constructor(maxAttempts: number, minimumIntervalMs: number) {
    if (!Number.isInteger(maxAttempts) || maxAttempts < 1 || minimumIntervalMs < 0) {
      throw new Error("Limites de ação inválidos");
    }
    this.#maxAttempts = maxAttempts;
    this.#minimumIntervalMs = minimumIntervalMs;
  }

  attempt(now = Date.now()): ActionAttemptDecision {
    if (this.#attempts >= this.#maxAttempts) return { allowed: false, waitMs: 0, exhausted: true };
    const waitMs = Math.max(0, this.#lastAttemptAt + this.#minimumIntervalMs - now);
    if (waitMs > 0) return { allowed: false, waitMs, exhausted: false };
    this.#attempts += 1;
    this.#lastAttemptAt = now;
    return { allowed: true, waitMs: 0, exhausted: false };
  }

  reset(): void {
    this.#attempts = 0;
    this.#lastAttemptAt = 0;
  }

  attempts(): number {
    return this.#attempts;
  }
}
