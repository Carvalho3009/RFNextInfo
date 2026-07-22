import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { extname, isAbsolute, join, normalize, relative, resolve } from "node:path";
import type { AppConfig } from "./config.js";
import type { SafeLogger } from "./logger.js";
import { sanitizeErrorMessage, tokensMatch } from "./security.js";
import type { SupervisorRegistry } from "./supervisor.js";

const CONTENT_TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

export function createDashboardServer(
  config: AppConfig,
  registry: SupervisorRegistry,
  logger: SafeLogger,
  dashboardDir = resolve("dist/dashboard"),
): Server {
  const clients = new Set<ServerResponse>();
  const authLimiter = new FailedAuthLimiter();
  const unsubscribe = registry.subscribe((statuses) => {
    const payload = `data: ${JSON.stringify(statuses)}\n\n`;
    for (const client of clients) client.write(payload);
  });

  const server = createServer((request, response) => {
    void handleRequest(request, response, config, registry, logger, dashboardDir, clients, authLimiter);
  });
  server.on("close", () => {
    unsubscribe();
    for (const client of clients) client.end();
  });
  return server;
}

async function handleRequest(
  request: IncomingMessage,
  response: ServerResponse,
  config: AppConfig,
  registry: SupervisorRegistry,
  logger: SafeLogger,
  dashboardDir: string,
  clients: Set<ServerResponse>,
  authLimiter: FailedAuthLimiter,
): Promise<void> {
  try {
    const requestUrl = new URL(request.url ?? "/", `http://${request.headers.host ?? "localhost"}`);
    if (request.method === "GET" && requestUrl.pathname === "/healthz") {
      sendJson(response, 200, { status: "ok", timestamp: new Date().toISOString() });
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/readyz") {
      const statuses = registry.statuses();
      const enabledIds = new Set(config.instances.filter((instance) => instance.enabled).map((instance) => instance.id));
      const unhealthy = statuses.filter((status) => enabledIds.has(status.id) && (!status.running || status.state !== "MONITOR_COMBAT"));
      sendJson(response, unhealthy.length ? 503 : 200, {
        status: unhealthy.length ? "degraded" : "ready",
        enabled: enabledIds.size,
        unhealthy: unhealthy.length,
        timestamp: new Date().toISOString(),
      });
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/api/instances") {
      if (!authorizeOrReply(request, response, authLimiter)) return;
      sendJson(response, 200, registry.statuses());
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/api/events") {
      if (!authorizeOrReply(request, response, authLimiter)) return;
      response.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Content-Type-Options": "nosniff",
      });
      response.write(`data: ${JSON.stringify(registry.statuses())}\n\n`);
      clients.add(response);
      request.on("close", () => clients.delete(response));
      return;
    }

    const commandMatch = requestUrl.pathname.match(/^\/api\/instances\/([a-z0-9_-]+)\/(start|stop|restart)$/);
    if (request.method === "POST" && commandMatch) {
      if (!sameOrigin(request)) return unauthorized(response);
      if (!authorizeOrReply(request, response, authLimiter)) return;
      const id = commandMatch[1];
      const command = commandMatch[2];
      if (!id || !command) return sendJson(response, 400, { error: "Comando inválido" });
      if (command === "start") await registry.start(id);
      if (command === "stop") await registry.stop(id);
      if (command === "restart") await registry.restart(id);
      logger.info("dashboard_command", { instanceId: id, command });
      sendJson(response, 202, { accepted: true });
      return;
    }

    if (request.method === "GET") {
      await serveStatic(response, dashboardDir, requestUrl.pathname);
      return;
    }
    sendJson(response, 404, { error: "Não encontrado" });
  } catch (error) {
    const message = sanitizeErrorMessage(error);
    logger.error("dashboard_request_failed", { message });
    sendJson(response, 500, { error: "Erro interno" });
  }
}

function authorized(request: IncomingMessage): boolean {
  const expected = process.env.POKEIDLE_DASHBOARD_TOKEN;
  if (!expected) return false;
  const headerToken = request.headers["x-dashboard-token"];
  const bearer = request.headers.authorization?.replace(/^Bearer\s+/i, "");
  const actual = (Array.isArray(headerToken) ? headerToken[0] : headerToken) ?? bearer;
  return tokensMatch(actual, expected);
}

function authorizeOrReply(request: IncomingMessage, response: ServerResponse, limiter: FailedAuthLimiter): boolean {
  const client = request.socket.remoteAddress ?? "unknown";
  if (limiter.isBlocked(client)) {
    sendJson(response, 429, { error: "Muitas tentativas de autenticação" });
    return false;
  }
  if (!authorized(request)) {
    limiter.recordFailure(client);
    unauthorized(response);
    return false;
  }
  limiter.clear(client);
  return true;
}

function sameOrigin(request: IncomingMessage): boolean {
  const origin = request.headers.origin;
  if (!origin) return true;
  try {
    return new URL(origin).host === request.headers.host;
  } catch {
    return false;
  }
}

function unauthorized(response: ServerResponse): void {
  sendJson(response, 401, { error: "Token do dashboard ausente ou inválido" });
}

function sendJson(response: ServerResponse, status: number, value: unknown): void {
  if (response.headersSent) return;
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'",
  });
  response.end(JSON.stringify(value));
}

async function serveStatic(response: ServerResponse, dashboardDir: string, pathname: string): Promise<void> {
  const root = resolve(dashboardDir);
  const normalized = normalize(decodeURIComponent(pathname)).replace(/^(?:\.\.[/\\])+/, "");
  let filePath = resolve(root, normalized.replace(/^[/\\]+/, ""));
  const relativePath = relative(root, filePath);
  if (relativePath.startsWith("..") || isAbsolute(relativePath)) return sendJson(response, 403, { error: "Caminho inválido" });
  const fileStat = await stat(filePath).catch(() => null);
  if (!fileStat?.isFile()) filePath = join(root, "index.html");
  const finalStat = await stat(filePath).catch(() => null);
  if (!finalStat?.isFile()) return sendJson(response, 503, { error: "Dashboard ainda não foi compilado" });
  response.writeHead(200, {
    "Content-Type": CONTENT_TYPES[extname(filePath)] ?? "application/octet-stream",
    "Cache-Control": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy":
      "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
  });
  createReadStream(filePath).pipe(response);
}

class FailedAuthLimiter {
  readonly #entries = new Map<string, { failures: number; windowStartedAt: number; blockedUntil: number }>();

  recordFailure(client: string, now = Date.now()): void {
    const previous = this.#entries.get(client);
    const entry = !previous || now - previous.windowStartedAt > 60_000
      ? { failures: 0, windowStartedAt: now, blockedUntil: 0 }
      : previous;
    entry.failures += 1;
    if (entry.failures >= 5) entry.blockedUntil = now + 60_000;
    this.#entries.set(client, entry);
  }

  isBlocked(client: string, now = Date.now()): boolean {
    return (this.#entries.get(client)?.blockedUntil ?? 0) > now;
  }

  clear(client: string): void {
    this.#entries.delete(client);
  }
}
