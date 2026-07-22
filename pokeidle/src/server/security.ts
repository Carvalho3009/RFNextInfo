import { timingSafeEqual } from "node:crypto";

const SLEEP_MODE_PATTERN = /(?:zzz|sleep(?:[-_\s]?mode)?|nap|soneca|dormir|modo[-_\s]?sono|offline|💤)/iu;
const FORBIDDEN_ACTION_PATTERN =
  /(?:\b(?:chat|pvp|diamonds?|diamantes?|gems?|gemas?|gold|ouro|buy|purchase|shop|store|loja|compr(?:ar|a|e|as|ando)|pagar|turbo|boost|premium|vip|retention|cl[aã])\b|💎)/iu;
const SENSITIVE_KEY_PATTERN =
  /password|passwd|authorization|cookie|set-cookie|token|secret|storageState|session|credential/i;
const JWT_PATTERN = /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]{8,})?\b/g;
const EMBEDDED_SECRET_PATTERN =
  /\b(password|passwd|authorization|cookie|set-cookie|token|secret|storageState|session|credential)\b\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)/giu;
const AUTH_SCHEME_PATTERN = /\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+/giu;
const URL_PATTERN = /\b(?:https?|wss?):\/\/[^\s"'<>]+/giu;
const POSITIONAL_SELECTOR_PATTERN = /(?::nth-(?:child|of-type)|:first-(?:child|of-type)|:last-(?:child|of-type)|\bnth\s*=|>>\s*nth)/iu;
const STABLE_SELECTOR_ANCHOR_PATTERN = /(?:#[A-Za-z_][\w-]*|\[(?:data-[\w-]+|aria-[\w-]+|name|role|id)\s*(?:[~|^$*]?=)?)/u;

export type AllowedGameAction =
  | "activate_auto_potion"
  | "activate_auto_revive"
  | "start_hunt"
  | "resume_hunt";

export function assertSelectorPolicy(selector: string): void {
  if (!selector) return;
  if (SLEEP_MODE_PATTERN.test(selector) || FORBIDDEN_ACTION_PATTERN.test(selector)) {
    throw new Error("Seletor recusado pela política de segurança");
  }
  if (selector.length > 512 || POSITIONAL_SELECTOR_PATTERN.test(selector)) {
    throw new Error("Seletor posicional ou excessivamente longo recusado pela política de segurança");
  }
  if (!STABLE_SELECTOR_ANCHOR_PATTERN.test(selector)) {
    throw new Error("Seletor sem âncora estável recusado pela política de segurança");
  }
}

export function assertAccessibleTargetSafe(label: string): void {
  if (!label.trim()) {
    throw new Error("POLICY_BLOCK: alvo sem nome acessível computado");
  }
  if (SLEEP_MODE_PATTERN.test(label)) {
    throw new Error("POLICY_BLOCK: alvo relacionado ao Modo Soneca");
  }
  if (FORBIDDEN_ACTION_PATTERN.test(label)) {
    throw new Error("POLICY_BLOCK: alvo proibido ou com gasto potencial");
  }
}

export function assertAccessibleTargetMatches(actual: string, expected: string): void {
  assertAccessibleTargetSafe(actual);
  assertAccessibleTargetSafe(expected);
  if (normalizeAccessibleName(actual) !== normalizeAccessibleName(expected)) {
    throw new Error("POLICY_BLOCK: nome acessível do alvo divergiu do contrato autenticado");
  }
}

export function sanitizeErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : typeof error === "string" ? error : "Falha desconhecida";
  return redactText(message).slice(0, 500);
}

export function sanitizeUrl(value: string): string {
  try {
    const url = new URL(value);
    return `${url.origin}${url.pathname}`;
  } catch {
    return "[url-redacted]";
  }
}

export function redact(value: unknown, key = ""): unknown {
  if (SENSITIVE_KEY_PATTERN.test(key)) return "[REDACTED]";
  if (typeof value === "string") return redactText(value);
  if (Array.isArray(value)) return value.map((item) => redact(item));
  if (value && typeof value === "object") {
    const output: Record<string, unknown> = {};
    for (const [childKey, childValue] of Object.entries(value)) {
      output[childKey] = redact(childValue, childKey);
    }
    return output;
  }
  return value;
}

export function tokensMatch(actual: string | undefined, expected: string | undefined): boolean {
  if (!actual || !expected) return false;
  const left = Buffer.from(actual);
  const right = Buffer.from(expected);
  return left.length === right.length && timingSafeEqual(left, right);
}

export function assertDashboardTokenStrong(token: string | undefined): asserts token is string {
  if (!token || Buffer.byteLength(token, "utf8") < 32 || Buffer.byteLength(token, "utf8") > 512) {
    throw new Error("POKEIDLE_DASHBOARD_TOKEN deve conter entre 32 e 512 bytes");
  }
}

function redactText(value: string): string {
  return value
    .replace(JWT_PATTERN, "[REDACTED_TOKEN]")
    .replace(AUTH_SCHEME_PATTERN, "[REDACTED_AUTH]")
    .replace(EMBEDDED_SECRET_PATTERN, (_match, key: string) => `${key}=[REDACTED]`)
    .replace(URL_PATTERN, (url) => sanitizeUrl(url));
}

function normalizeAccessibleName(value: string): string {
  return value.trim().replace(/\s+/g, " ").normalize("NFKC").toLocaleLowerCase("pt-BR");
}

export const policyPatternsForTests = {
  sleep: SLEEP_MODE_PATTERN,
  forbidden: FORBIDDEN_ACTION_PATTERN,
};
