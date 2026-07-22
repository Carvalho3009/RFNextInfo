import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { loadConfig, resolveDataDir } from "./config.js";
import type { InstanceStatus } from "./types.js";

const command = process.argv[2];
if (!command || !["stop", "restart", "status", "logs"].includes(command)) {
  throw new Error("Uso: cli <stop|restart|status|logs>");
}

const config = await loadConfig();
const baseUrl = `http://${config.dashboard.host}:${config.dashboard.port}`;

if (command === "logs") {
  const logFiles = ["supervisor", ...config.instances.map((instance) => instance.id)];
  for (const name of logFiles) {
    const path = join(resolveDataDir(config), "logs", `${name}.ndjson`);
    const content = await readFile(path, "utf8").catch(() => "");
    const lines = content.trim().split(/\r?\n/).filter(Boolean).slice(-50);
    if (lines.length) process.stdout.write(`\n# ${name}\n${lines.join("\n")}\n`);
  }
} else {
  const response = await fetch(`${baseUrl}/api/instances`, {
    headers: tokenHeaders(),
  });
  if (!response.ok) throw new Error(`Dashboard respondeu ${response.status}`);
  const statuses = (await response.json()) as InstanceStatus[];
  if (command === "status") {
    process.stdout.write(`${JSON.stringify(statuses, null, 2)}\n`);
  } else {
    await Promise.all(
      statuses.map(async (status) => {
        const action = command === "stop" ? "stop" : "restart";
        const result = await fetch(`${baseUrl}/api/instances/${status.id}/${action}`, {
          method: "POST",
          headers: tokenHeaders(),
        });
        if (!result.ok) throw new Error(`${status.id}: ${result.status}`);
      }),
    );
    process.stdout.write(`${command === "stop" ? "Parada" : "Reinício"} solicitado para ${statuses.length} instância(s).\n`);
  }
}

function tokenHeaders(): Record<string, string> {
  const token = process.env.POKEIDLE_DASHBOARD_TOKEN;
  if (!token) throw new Error("POKEIDLE_DASHBOARD_TOKEN não definido");
  return { "x-dashboard-token": token };
}
