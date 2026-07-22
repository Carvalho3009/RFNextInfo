import type { InstanceStatus } from "./types";

const TOKEN_KEY = "pokeidle-dashboard-token";

export function readToken(): string {
  return sessionStorage.getItem(TOKEN_KEY) ?? "";
}

export function saveToken(token: string): void {
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
}

export async function commandInstance(
  id: string,
  command: "start" | "stop" | "restart",
): Promise<void> {
  const response = await fetch(`/api/instances/${encodeURIComponent(id)}/${command}`, {
    method: "POST",
    headers: { "x-dashboard-token": readToken() },
  });
  if (!response.ok) throw new Error(response.status === 401 ? "Token inválido" : `Falha HTTP ${response.status}`);
}

export function subscribeInstances(
  onUpdate: (instances: InstanceStatus[]) => void,
  onError: (error: Error) => void,
): () => void {
  const controller = new AbortController();
  void (async () => {
    try {
      const response = await fetch("/api/events", {
        headers: readToken() ? { "x-dashboard-token": readToken() } : {},
        signal: controller.signal,
      });
      if (!response.ok || !response.body) throw new Error(`Stream indisponível (${response.status})`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (!controller.signal.aborted) {
        const { value, done } = await reader.read();
        if (done) throw new Error("Stream de status foi encerrado");
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const event of events) {
          const data = event.split("\n").find((line) => line.startsWith("data: "))?.slice(6);
          if (data) onUpdate(JSON.parse(data) as InstanceStatus[]);
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) onError(error instanceof Error ? error : new Error("Stream interrompido"));
    }
  })();
  return () => controller.abort();
}
