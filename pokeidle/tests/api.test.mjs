import assert from "node:assert/strict";
import { test } from "node:test";
import { createDashboardServer } from "../dist/server/api.js";

test("API protege leitura e mutação, mantendo health checks sem segredo", async () => {
  const previousToken = process.env.POKEIDLE_DASHBOARD_TOKEN;
  process.env.POKEIDLE_DASHBOARD_TOKEN = "t".repeat(40);
  const status = {
    id: "principal", accountLabel: "conta•••", environment: "test", state: "MONITOR_COMBAT", tone: "healthy",
    running: true, pid: 1, startedAt: new Date().toISOString(), lastHeartbeat: new Date().toISOString(), reason: null,
    restartCount: 0, circuitOpenUntil: null, observation: null, latestMetric: null, metrics: [],
  };
  let commands = 0;
  const registry = {
    subscribe: () => () => undefined,
    statuses: () => [status],
    start: async () => { commands += 1; },
    stop: async () => { commands += 1; },
    restart: async () => { commands += 1; },
  };
  const logger = { info: () => undefined, error: () => undefined };
  const config = { instances: [{ id: "principal", enabled: true }] };
  const server = createDashboardServer(config, registry, logger);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  try {
    assert.equal((await fetch(`${baseUrl}/healthz`)).status, 200);
    assert.equal((await fetch(`${baseUrl}/readyz`)).status, 200);
    assert.equal((await fetch(`${baseUrl}/api/instances`)).status, 401);
    const headers = { "x-dashboard-token": process.env.POKEIDLE_DASHBOARD_TOKEN };
    assert.equal((await fetch(`${baseUrl}/api/instances`, { headers })).status, 200);
    assert.equal((await fetch(`${baseUrl}/api/instances/principal/restart`, { method: "POST", headers })).status, 202);
    assert.equal(commands, 1);
    for (let index = 0; index < 5; index += 1) {
      await fetch(`${baseUrl}/api/instances`, { headers: { "x-dashboard-token": "inválido" } });
    }
    assert.equal((await fetch(`${baseUrl}/api/instances`, { headers: { "x-dashboard-token": "inválido" } })).status, 429);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    if (previousToken === undefined) delete process.env.POKEIDLE_DASHBOARD_TOKEN;
    else process.env.POKEIDLE_DASHBOARD_TOKEN = previousToken;
  }
});
