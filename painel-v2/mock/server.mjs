#!/usr/bin/env node
// Mock do control-api (SPEC-002/008/009/010/013) — Node http puro, sem deps.
// Replica os shapes consumidos pelo painel v1 (static/index.html, orch.js, chat.js).
// Uso: CONTROL_TOKEN é fixo em "test-token" para simplificar o teste local do painel.
"use strict";

import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const PORT = 8000;
const TOKEN = "test-token";
const V2_INDEX_PATH = "/home/user/v2/index.html";

// ------------------------- estado em memória -------------------------

let nextServerId = 3;
const mcpServers = [
  { id: 1, name: "local-ai", url: "http://host.docker.internal:8000/mcp",
    enabled: true, has_auth: false, auth_expires_at: null },
  { id: 2, name: "asana", url: "https://mcp.asana.com/mcp",
    enabled: true, has_auth: true,
    // expirado de propósito p/ exercitar o fluxo de reautenticação no painel
    auth_expires_at: new Date(Date.now() - 3 * 3600_000).toISOString() },
];

const INSTALLED_MODELS = [
  { name: "qwen3-coder:30b", parameter_size: "30B", quantization_level: "Q4_K_M", size_gb: 19.2 },
  { name: "gpt-oss:20b", parameter_size: "20B", quantization_level: "Q4_K_M", size_gb: 12.8 },
  { name: "deepseek-r1:32b", parameter_size: "32B", quantization_level: "Q4_K_M", size_gb: 20.5 },
  { name: "qwen3:8b", parameter_size: "8B", quantization_level: "Q5_K_M", size_gb: 5.7 },
  { name: "mistral-small:24b", parameter_size: "24B", quantization_level: "Q4_K_M", size_gb: 15.1 },
  { name: "qwen3-vl:8b", parameter_size: "8B", quantization_level: "Q5_K_M", size_gb: 6.1 },
];

// modelos atualmente carregados (loaded) — VRAM/expires_at; ollama_unload remove daqui
let ollamaRunning = [
  { name: "qwen3-coder:30b", size_vram: 19_500_000_000, expires_at: new Date(Date.now() + 4 * 60_000).toISOString() },
  { name: "qwen3:8b", size_vram: 6_100_000_000, expires_at: new Date(Date.now() + 9 * 60_000).toISOString() },
];

const containers = {
  "mcp-control": { image: "ghcr.io/casa/mcp-control:latest", state: "running", status: "Up 6 hours" },
  "mcp-db": { image: "postgres:16-alpine", state: "running", status: "Up 6 hours" },
  "cloudflared": { image: "cloudflare/cloudflared:latest", state: "restarting", status: "Restarting (1) 12 seconds ago" },
};

// GET /api/workers — workers disponíveis (ollama + CLIs com heartbeat do host-worker)
function buildWorkers() {
  const ollamaWorkers = INSTALLED_MODELS.map(m => ({
    type: "ollama", model: m.name, cost: "grátis (GPU local)",
  }));
  return [
    ...ollamaWorkers,
    { type: "cli", model: "cli:claude", cost: "pago (plano Claude)",
      models: ["claude-fable-5", "opus", "sonnet"],
      last_heartbeat: new Date(Date.now() - 8_000).toISOString() },
    { type: "cli", model: "cli:codex", cost: "pago (plano OpenAI)",
      models: ["gpt-5.6-sol", "gpt-5.6-terra"],
      last_heartbeat: new Date(Date.now() - 14_000).toISOString() },
    // sem heartbeat recente do host-worker: presente na config, mas sem modelos reportados
    { type: "cli", model: "cli:gemini", cost: "pago (plano Google)",
      models: [], last_heartbeat: null },
  ];
}

let instructionsText = `# Instruções permanentes — MCP CASA

Servidas a todos os clientes (Claude, ChatGPT, Gemini, painel de controle) via \`get_instructions\`.

## Regras gerais
- Consulte \`memory_search\` antes de perguntar algo que já pode ter sido informado.
- Salve decisões e fatos duráveis com \`memory_save\`.
- Rode múltiplas gerações em paralelo quando possível (2 a 4 por vez para não estourar a VRAM).

_(texto de exemplo — editável via set_instructions)_
`;

const TOOLS = [
  {
    name: "get_instructions",
    description: "Devolve o conteúdo atual das instruções permanentes (markdown).",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "set_instructions",
    description: "Substitui o conteúdo das instruções permanentes.\nBackup automático em .bak antes de gravar.",
    input_schema: {
      type: "object",
      properties: { content: { type: "string", description: "novo conteúdo markdown" } },
      required: ["content"],
    },
  },
  {
    name: "ollama_unload",
    description: "Descarrega um modelo do Ollama, liberando RAM/VRAM imediatamente.",
    input_schema: {
      type: "object",
      properties: { model: { type: "string", description: "nome do modelo (ex.: qwen3:8b)" } },
      required: ["model"],
    },
  },
  {
    name: "memory_search",
    description: "Busca semântica na memória compartilhada entre clientes.",
    input_schema: {
      type: "object",
      properties: {
        query: { type: "string", description: "texto de busca" },
        k: { type: "integer", description: "máximo de resultados", default: 5 },
      },
      required: ["query"],
    },
  },
];

let nextRunId = 6;
const runs = [
  { id: 1, created_at: iso(-3600_000 * 5), server: "local-ai", tool: "get_instructions", args: {}, ok: true, ms: 42, result: { content: "(instruções anteriores)" } },
  { id: 2, created_at: iso(-3600_000 * 4), server: "local-ai", tool: "memory_search", args: { query: "config do worker codex", k: 5 }, ok: true, ms: 118, result: { results: [] } },
  { id: 3, created_at: iso(-3600_000 * 2), server: "local-ai", tool: "ollama_unload", args: { model: "mistral-small:24b" }, ok: true, ms: 890, result: { ok: true } },
  { id: 4, created_at: iso(-3600_000), server: "asana", tool: "list_tasks", args: { project: "roadmap" }, ok: false, ms: 205, error: "Token expirado para asana; refaça a autenticação (PUT /api/mcp/servers/2/auth)." },
  { id: 5, created_at: iso(-600_000), server: "local-ai", tool: "set_instructions", args: { content: "(novo texto)" }, ok: true, ms: 37, result: { ok: true } },
];

let nextHostCmdId = 5;
const hostCommands = [
  { id: 1, action: "compose_up", status: "done", created_at: iso(-3600_000 * 6), result: "containers atualizados" },
  { id: 2, action: "renew_design_token", status: "failed", created_at: iso(-3600_000 * 3), result: "erro: refresh_token expirado" },
  { id: 3, action: "restart_worker", status: "running", created_at: iso(-30_000), result: null },
  { id: 4, action: "compose_build_control", status: "queued", created_at: iso(-5_000), result: null },
];

// ------------------------- FASE 2: projetos -------------------------

let nextProjectId = 4;
const projects = [
  { id: 1, slug: "pokeidle", title: "PokeIdle", description: "Jogo idle de captura — protótipo solo.", created_at: iso(-86400_000 * 40) },
  { id: 2, slug: "rooc-americas", title: "ROOC Américas", description: "Identidade visual Karvalho e mockups do stack.", created_at: iso(-86400_000 * 25) },
  { id: 3, slug: "painel-v2", title: "Painel MCP v2", description: "Rework do painel de controle (SPEC-014/017).", created_at: iso(-86400_000 * 10) },
];

// ------------------------- FASE 2: uso/custos -------------------------

const usageModels = {
  "claude-fable-5": { tokens_in_today: 4200, tokens_out_today: 15800, tokens_in_7d: 31500, tokens_out_7d: 118200, accepts_7d: 6, runs_7d: 9 },
  "gpt-5.6-sol": { tokens_in_today: 1800, tokens_out_today: 9100, tokens_in_7d: 22300, tokens_out_7d: 96700, accepts_7d: 4, runs_7d: 11 },
  "qwen3-coder:30b": { tokens_in_today: 6100, tokens_out_today: 12400, tokens_in_7d: 40200, tokens_out_7d: 88900, accepts_7d: 8, runs_7d: 22 },
  "gpt-oss:20b": { tokens_in_today: 900, tokens_out_today: 3100, tokens_in_7d: 7600, tokens_out_7d: 19800, accepts_7d: 1, runs_7d: 6 },
};
const lastRateLimit = {
  "gpt-5.6-sol": iso(-40 * 60_000), // bateu limite do provedor há 40min
};
const designCalls = { today: 3, "7d": 11 }; // uso de mcp__claude-design__* (pattern "design")

function usageKeyFor(model) {
  if (!model) return model;
  return model.includes("/") ? model.split("/")[1] : model.replace(/^cli:/, "");
}
function bumpUsageOnRun(model, tokensIn, tokensOut) {
  const key = usageKeyFor(model);
  if (!usageModels[key]) {
    usageModels[key] = { tokens_in_today: 0, tokens_out_today: 0, tokens_in_7d: 0, tokens_out_7d: 0, accepts_7d: 0, runs_7d: 0 };
  }
  const u = usageModels[key];
  u.tokens_in_today += tokensIn; u.tokens_out_today += tokensOut;
  u.tokens_in_7d += tokensIn; u.tokens_out_7d += tokensOut;
  u.runs_7d += 1;
}
function bumpUsageOnAccept(model) {
  const key = usageKeyFor(model);
  if (usageModels[key]) usageModels[key].accepts_7d += 1;
}

// ------------------------- FASE 2: orquestrador -------------------------

const PAINEL_V2_BRIEF = `# BRIEF — F6 SPEC-014: Design do Painel do MCP v2 (levantamento de design)

Você é um agente de design/arquitetura de UI. Produza uma **proposta de design completa** para o rework do painel de controle do stack MCP local ("MCP Control"). [...] Restrição dura: as rotas do control-api NÃO mudam. A migração será aba por aba sobre a API existente.

## Abas obrigatórias
Status, Workers, Tools, Orquestrador, Chat/projetos, Grill Me, Uso/custos, Instruções.
[texto completo do brief truncado no mock — ver /home/user/proposta-fable.md e /home/user/proposta-gpt-5.6-sol.md]`;

const FAKE_ORCH = {
  gen: (prompt) => `Aqui está minha proposta para:\n\n> ${prompt.slice(0, 120)}${prompt.length > 120 ? "…" : ""}\n\n1. Levantamento dos requisitos principais.\n2. Abordagem sugerida, com trade-offs explícitos.\n3. Próximos passos recomendados.`,
  critic: () => `**Pontos fortes:** estrutura clara, cobre os requisitos citados.\n**Riscos:** falta detalhar o caso de erro/offline; validar com o owner antes de codar.`,
  final: (prompt) => `Versão revisada considerando a crítica:\n\n> ${prompt.slice(0, 120)}${prompt.length > 120 ? "…" : ""}\n\nAjustei a seção de riscos e adicionei o caso de offline.`,
  judge: () => `Comparando as respostas: a primeira é mais completa em cobertura; a segunda é mais concisa. Escolho mesclar os pontos fortes de ambas como resposta final.`,
};
function fakeThinking(level) {
  if (level !== "high" && level !== "medium") return undefined;
  return "Analisando o prompt... considerando alternativas... convergindo na abordagem mais simples que atende os requisitos.";
}

let nextJobId = 239;
let nextResultId = 260;
const jobs = new Map();
function seedJob(j) { jobs.set(j.id, j); }

seedJob({
  id: 233, pattern: "fanout", status: "done", prompt: PAINEL_V2_BRIEF,
  params: { project_slug: "painel-v2", system_prompt: "", thinking_level: "high", max_output_tokens: 12000 },
  project_id: 3, created_at: "2026-07-18T20:24:48.599Z", finished_at: "2026-07-18T20:28:38.742Z",
  results: [{
    id: 249, worker: "cli", model: "cli:claude/claude-fable-5", role: "gen",
    response: "Segue a proposta de design completa. Não precisei de ferramentas — todo o insumo está no brief; os valores de contraste citados na seção 7 foram calculados a partir dos hex fornecidos.\n\n---\n\n# Proposta de Design — MCP Control v2 (identidade Karvalho)\n\n## 1. Conceito\n\n**\"Sala de máquinas com moldura editorial: o ornamento vive na casca, o dado vive nu.\"**\n\n[...] resposta truncada no mock — íntegra em /home/user/proposta-fable.md",
    error: null, tokens_in: 2, tokens_out: 15038, ms: 230141, accepted: false,
  }],
});
seedJob({
  id: 234, pattern: "fanout", status: "done", prompt: PAINEL_V2_BRIEF,
  params: { project_slug: "painel-v2", system_prompt: "", thinking_level: "high", max_output_tokens: 12000 },
  project_id: 3, created_at: "2026-07-18T20:24:50.150Z", finished_at: "2026-07-18T20:28:38.291Z",
  results: [{
    id: 248, worker: "cli", model: "cli:codex/gpt-5.6-sol", role: "gen",
    response: "## 1. Conceito\n\n**Console editorial operacional:** a personalidade Karvalho organiza o painel sem competir com os dados.\n\n- Observação primeiro; ações e edição aparecem apenas no contexto necessário.\n- Hierarquia por tipografia, alinhamento e bordas — não por uma grade indiscriminada de cards.\n\n[...] resposta truncada no mock — íntegra em /home/user/proposta-gpt-5.6-sol.md",
    error: null, tokens_in: 0, tokens_out: 0, ms: 228139, accepted: false,
  }],
});
seedJob({
  id: 235, pattern: "judge", status: "done",
  prompt: "Revisar a SPEC-017 antes de aprovar: consistência entre as 8 abas do mockup e os contratos do control-api.",
  params: { system_prompt: "", thinking_level: "medium", temperature: 0.2, max_output_tokens: 4096, judge_model: "qwen3-coder:30b" },
  project_id: 3, created_at: iso(-86400_000 * 2), finished_at: iso(-86400_000 * 2 + 900_000),
  results: [
    { id: 250, worker: "cli", model: "cli:claude/claude-fable-5", role: "gen", response: FAKE_ORCH.gen("Revisar a SPEC-017 antes de aprovar"), thinking: fakeThinking("medium"), error: null, tokens_in: 1200, tokens_out: 3400, ms: 41200, accepted: false },
    { id: 251, worker: "cli", model: "cli:codex/gpt-5.6-sol", role: "gen", response: FAKE_ORCH.gen("Revisar a SPEC-017 antes de aprovar (2ª opinião)"), error: null, tokens_in: 980, tokens_out: 2900, ms: 38900, accepted: true },
    { id: 252, worker: "ollama", model: "qwen3-coder:30b", role: "judge", response: FAKE_ORCH.judge(), error: null, tokens_in: 2400, tokens_out: 700, ms: 15300, accepted: false },
  ],
});
seedJob({
  id: 236, pattern: "design", status: "running",
  prompt: "Gerar mockup navegável da aba Workers (matriz papéis×worker) a partir da SPEC-017 §4.2.",
  params: { system_prompt: "", thinking_level: "low", temperature: 0.2, max_output_tokens: 8000, project_slug: "painel-v2", allowed_tools: ["mcp__claude-design__*"] },
  project_id: 3, created_at: iso(-90_000), finished_at: null, results: [],
});
seedJob({
  id: 237, pattern: "fanout", status: "failed",
  prompt: "Resumir os logs de erro do host-worker das últimas 24h e apontar causa raiz.",
  params: { system_prompt: "", thinking_level: "off", temperature: 0.1, max_output_tokens: 2048 },
  project_id: null, created_at: iso(-3600_000 * 5), finished_at: iso(-3600_000 * 5 + 5200),
  results: [{ id: 253, worker: "ollama", model: "gpt-oss:20b", role: "gen", response: null, error: "Ollama retornou 500: modelo descarregado durante a geração.", tokens_in: 0, tokens_out: 0, ms: 5200, accepted: false }],
});
seedJob({
  id: 238, pattern: "critic", status: "canceled",
  prompt: "Traduzir o doc de onboarding do CASA de PT para EN, mantendo termos técnicos.",
  params: { system_prompt: "", thinking_level: "low", temperature: 0.1, max_output_tokens: 2048 },
  project_id: null, created_at: iso(-1800_000), finished_at: iso(-1780_000),
  results: [{ id: 254, worker: "cli", model: "cli:gemini", role: "gen", response: "(cancelado antes de concluir)", error: null, tokens_in: 0, tokens_out: 0, ms: 1200, accepted: false }],
});

function jobSummary(j) { const { results, _timer, ...rest } = j; return rest; }
function jobPublic(j) { const { _timer, ...rest } = j; return rest; }

function makeResult(worker, role, response, thinking) {
  const model = worker.cli_model ? `${worker.model}/${worker.cli_model}` : worker.model;
  const r = {
    id: nextResultId++, worker: worker.type || "ollama", model, role, response, error: null,
    tokens_in: randMs(200, 2500), tokens_out: randMs(400, 4000), ms: randMs(3000, 60000), accepted: false,
  };
  if (thinking) r.thinking = thinking;
  return r;
}

function scheduleJobCompletion(job, workers) {
  job._timer = setTimeout(() => {
    const thinking = fakeThinking(job.params && job.params.thinking_level);
    if (job.pattern === "critic") {
      const w0 = workers[0], w1 = workers[1] || workers[0];
      job.results.push(makeResult(w0, "gen", FAKE_ORCH.gen(job.prompt), thinking));
      job.results.push(makeResult(w1, "critic", FAKE_ORCH.critic(), undefined));
      job.results.push(makeResult(w0, "final", FAKE_ORCH.final(job.prompt), thinking));
    } else if (job.pattern === "judge") {
      for (const w of workers) job.results.push(makeResult(w, "gen", FAKE_ORCH.gen(job.prompt), thinking));
      const judgeModel = (job.params && job.params.judge_model) || (workers[0] && workers[0].model) || "qwen3-coder:30b";
      job.results.push(makeResult({ type: "ollama", model: judgeModel }, "judge", FAKE_ORCH.judge(), undefined));
    } else {
      for (const w of workers) job.results.push(makeResult(w, "gen", FAKE_ORCH.gen(job.prompt), thinking));
    }
    job.status = "done";
    job.finished_at = new Date().toISOString();
    for (const r of job.results) bumpUsageOnRun(r.model, r.tokens_in, r.tokens_out);
    job._timer = null;
  }, 6000);
}

// ------------------------- FASE 2: chat -------------------------

let nextChatId = 505;
let nextTurnId = 900;
const chats = new Map();

function makeConv(id, worker_type, model, params, title, project_id, status) {
  const conv = {
    id, worker_type, model, params: params || {}, title: title || null,
    project_id: project_id != null ? Number(project_id) : null, status, archived: false,
    created_at: new Date().toISOString(), turns: [], _seq: 0, _idempotency: new Map(), _genTimer: null,
  };
  chats.set(id, conv);
  return conv;
}
function addTurn(conv, role, status, content, opts = {}) {
  conv._seq += 1;
  const t = { id: nextTurnId++, seq: conv._seq, role, status, content, error: opts.error || null, ms: opts.ms ?? null, meta: opts.meta || null };
  conv.turns.push(t);
  return t;
}
function toPublicConv(conv, opts = {}) {
  const { id, worker_type, model, params, title, project_id, status, archived, created_at } = conv;
  const out = { id, worker_type, model, params, title, project_id, status, archived, created_at };
  if (opts.includeTurns) {
    const afterSeq = opts.afterSeq || 0;
    out.turns = conv.turns.filter(t => t.seq > afterSeq).map(publicTurn);
  }
  return out;
}
function publicTurn(t) {
  const { id, seq, role, status, content, error, ms, meta } = t;
  return { id, seq, role, status, content, error, ms, meta };
}
function fakeChatReply(model, question) {
  return `Sobre "${question.slice(0, 90)}${question.length > 90 ? "…" : ""}": aqui está uma resposta de exemplo gerada pelo mock (modelo ${model}). Em produção isto viria do worker real.`;
}

// conversa #501: import ativo — gera ~4s depois de o servidor subir, p/ testar polling
const chat501 = makeConv(501, "cli", "cli:claude", { temperature: 0.4, max_output_tokens: 2048, thinking_level: "low", cli_model: "claude-fable-5" }, "Dúvidas sobre a SPEC-017", 3, "running");
addTurn(chat501, "user", "done", "As cores gold/acid do tema Karvalho já estão validadas em contraste WCAG?");
const chat501AssistantTurn = addTurn(chat501, "assistant", "running", "");
chat501._genTimer = setTimeout(() => {
  chat501AssistantTurn.status = "done";
  chat501AssistantTurn.content = "Sim — a SPEC-017 §6 lista os contrastes validados sobre coal/panel: bone 17,8:1, acid 16:1, gold 8,9:1, coral 6,8:1 (AA), violet 5:1. Todos passam AA; texto grande passa AAA.";
  chat501AssistantTurn.ms = 3850;
  chat501.status = "idle";
  chat501._genTimer = null;
}, 4000);

const chat502 = makeConv(502, "ollama", "qwen3-coder:30b", { temperature: 0.2, max_output_tokens: 2048, thinking_level: "low" }, "Refatorar mock server", null, "idle");
addTurn(chat502, "user", "done", "Como estruturar o outage mock sem travar o event loop do Node?");
addTurn(chat502, "assistant", "done", "Use req.socket.destroy() para simular queda de conexão e setTimeout/checagem de Date.now() para a janela de outage — nada bloqueante.", { ms: 2100 });

const chat503 = makeConv(503, "cli", "cli:codex", { temperature: 0.3, max_output_tokens: 2048, thinking_level: "medium", cli_model: "gpt-5.6-terra" }, null, 1, "needs_input");
addTurn(chat503, "user", "done", "Gera um plano de monetização pro PokeIdle.");
addTurn(chat503, "assistant", "done", "Preciso confirmar: o jogo terá IAP ou só ads? Isso muda a estrutura do plano.", { meta: { needs_input: true } });

const chat504 = makeConv(504, "ollama", "qwen3:8b", {}, "Rascunho antigo (arquivada)", null, "idle");
chat504.archived = true;
addTurn(chat504, "user", "done", "teste");
addTurn(chat504, "assistant", "done", "ok", { ms: 800 });

let outageUntil = 0; // epoch ms; enquanto Date.now() < outageUntil, /api/* falha

// ------------------------- utilidades -------------------------

function iso(deltaMs) { return new Date(Date.now() + deltaMs).toISOString(); }

function sendJson(res, status, body) {
  const data = Buffer.from(JSON.stringify(body), "utf-8");
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": data.length,
    "Access-Control-Allow-Origin": "*",
  });
  res.end(data);
}

function httpError(res, status, detail) {
  sendJson(res, status, { detail });
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", c => chunks.push(c));
    req.on("end", () => {
      if (!chunks.length) return resolve({});
      try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf-8"))); }
      catch { resolve({}); }
    });
    req.on("error", reject);
  });
}

function checkToken(req) {
  let token = req.headers["x-control-token"] || "";
  if (!token) {
    const auth = req.headers["authorization"] || "";
    if (auth.toLowerCase().startsWith("bearer ")) token = auth.slice(7);
  }
  return token === TOKEN;
}

// validador mínimo de JSON Schema (subset usado pelas tools acima)
function validateArgs(schema, args) {
  const props = schema.properties || {};
  const required = schema.required || [];
  for (const key of required) {
    if (args[key] === undefined) return `'${key}' é obrigatório`;
  }
  for (const [key, val] of Object.entries(args)) {
    const p = props[key];
    if (!p) continue;
    const t = p.type;
    if (t === "string" && typeof val !== "string") return `'${key}' deve ser string`;
    if (t === "integer" && !Number.isInteger(val)) return `'${key}' deve ser integer`;
    if (t === "number" && typeof val !== "number") return `'${key}' deve ser number`;
    if (t === "boolean" && typeof val !== "boolean") return `'${key}' deve ser boolean`;
  }
  return null;
}

function randMs(min, max) { return Math.floor(min + Math.random() * (max - min)); }

// ------------------------- handlers /api -------------------------

async function handleStatus(res) {
  const gpuUsed = 18_600 + Math.round(Math.random() * 800);
  sendJson(res, 200, {
    errors: [],
    system: {
      cpu: { usage_percent: +(20 + Math.random() * 40).toFixed(1), physical_cores: 16, logical_cores: 32 },
      memory: { usage_percent: +(45 + Math.random() * 20).toFixed(1), available_gb: 58.3, total_gb: 128 },
      workspace_disk: { usage_percent: 61.2, free_gb: 780, path: "/mnt/workspace" },
    },
    gpu: {
      available: true,
      gpus: [{
        index: 0, name: "NVIDIA GeForce RTX 4090",
        utilization_percent: +(30 + Math.random() * 50).toFixed(1),
        memory_used_mb: gpuUsed, memory_total_mb: 24576,
        temperature_c: 58 + Math.round(Math.random() * 10),
        power_draw_w: +(180 + Math.random() * 60).toFixed(1),
      }],
    },
    ollama: {
      installed: INSTALLED_MODELS,
      running: ollamaRunning,
    },
    containers: Object.entries(containers).map(([name, c]) => ({ name, ...c })),
  });
}

function handleWorkers(res) {
  sendJson(res, 200, buildWorkers());
}

function handleServersList(res) {
  sendJson(res, 200, mcpServers);
}

async function handleServerCreate(req, res) {
  const payload = await readBody(req);
  const name = String(payload.name || "").trim();
  const url = String(payload.url || "").trim();
  if (!name || !url.startsWith("http")) {
    return httpError(res, 422, "Informe name e url http(s) válidos.");
  }
  const srv = { id: nextServerId++, name, url, enabled: true, has_auth: false, auth_expires_at: null };
  mcpServers.push(srv);
  sendJson(res, 200, srv);
}

async function handleServerUpdate(req, res, id) {
  const srv = mcpServers.find(s => s.id === id);
  if (!srv) return httpError(res, 404, "Servidor não cadastrado.");
  const payload = await readBody(req);
  if (payload.enabled !== undefined) srv.enabled = !!payload.enabled;
  if (payload.url) srv.url = String(payload.url).trim();
  sendJson(res, 200, { ok: true });
}

function handleServerDelete(res, id) {
  const srv = mcpServers.find(s => s.id === id);
  if (!srv) return httpError(res, 404, "Servidor não cadastrado.");
  if (srv.name === "local-ai") {
    return httpError(res, 422, "O servidor local-ai é o padrão e não pode ser removido.");
  }
  const idx = mcpServers.indexOf(srv);
  mcpServers.splice(idx, 1);
  sendJson(res, 200, { ok: true });
}

async function handleServerAuth(req, res, id) {
  const srv = mcpServers.find(s => s.id === id);
  if (!srv) return httpError(res, 404, "Servidor não cadastrado.");
  const payload = await readBody(req);
  const auth = payload.auth === undefined ? null : payload.auth;
  if (auth !== null && !auth.access_token) {
    return httpError(res, 422, "auth.access_token é obrigatório (ou auth: null).");
  }
  srv.has_auth = auth !== null;
  srv.auth_expires_at = auth && auth.expires_at ? auth.expires_at
    : (auth ? new Date(Date.now() + 3600_000).toISOString() : null);
  sendJson(res, 200, { ok: true, has_auth: srv.has_auth });
}

function authIsExpired(srv) {
  return srv.has_auth && srv.auth_expires_at && new Date(srv.auth_expires_at).getTime() < Date.now();
}

function handleToolsList(res, id) {
  const srv = mcpServers.find(s => s.id === id);
  if (!srv) return httpError(res, 404, "Servidor não cadastrado.");
  if (authIsExpired(srv)) {
    return httpError(res, 502, `Token expirado para ${srv.name}; refaça a autenticação (PUT /api/mcp/servers/${srv.id}/auth).`);
  }
  if (srv.name !== "local-ai") {
    // servidor remoto genérico: mock devolve um catálogo vazio (sem tools conhecidas)
    return sendJson(res, 200, []);
  }
  sendJson(res, 200, TOOLS);
}

function runToolMocked(name, args) {
  switch (name) {
    case "get_instructions":
      return { content: instructionsText };
    case "set_instructions":
      instructionsText = String(args.content);
      return { ok: true };
    case "ollama_unload": {
      const before = ollamaRunning.length;
      ollamaRunning = ollamaRunning.filter(m => m.name !== args.model);
      return { ok: true, model: args.model, freed: before !== ollamaRunning.length };
    }
    case "memory_search": {
      const k = args.k || 5;
      const fake = [
        { id: 101, text: `Decisão relacionada a "${args.query}": usar SPEC-013 como referência.`, score: 0.91, created_at: iso(-86400_000 * 3) },
        { id: 87, text: `Nota: ${args.query} foi discutido no job #233.`, score: 0.77, created_at: iso(-86400_000 * 9) },
      ].slice(0, k);
      return { results: fake };
    }
    default:
      return { error: `tool desconhecida: ${name}` };
  }
}

async function handleToolRun(req, res, id, toolName) {
  const srv = mcpServers.find(s => s.id === id);
  if (!srv) return httpError(res, 404, "Servidor não cadastrado.");
  if (authIsExpired(srv)) {
    return httpError(res, 502, `Token expirado para ${srv.name}; refaça a autenticação (PUT /api/mcp/servers/${srv.id}/auth).`);
  }
  const catalog = srv.name === "local-ai" ? TOOLS : [];
  const tool = catalog.find(t => t.name === toolName);
  if (!tool) return httpError(res, 404, `Tool ${toolName} não existe em ${srv.name}.`);

  const payload = await readBody(req);
  const args = payload.args || {};
  const err = validateArgs(tool.input_schema, args);
  if (err) return httpError(res, 422, `Argumentos inválidos: ${err}`);

  const start = Date.now();
  const result = runToolMocked(toolName, args);
  const ms = Date.now() - start + randMs(15, 120);

  runs.unshift({ id: nextRunId++, created_at: new Date().toISOString(), server: srv.name, tool: toolName, args, ok: true, ms, result });
  if (runs.length > 50) runs.length = 50;

  sendJson(res, 200, { ok: true, ms, result });
}

function handleRuns(res, limit) {
  sendJson(res, 200, runs.slice(0, limit || 50));
}

const CONTAINER_ACTIONS = new Set(["start", "stop", "restart"]);

async function handleContainerAction(res, name, action) {
  if (!CONTAINER_ACTIONS.has(action)) {
    return httpError(res, 422, "Ação inválida. Use: ['restart', 'start', 'stop']");
  }
  const c = containers[name];
  if (!c) return httpError(res, 404, `Docker: no such container: ${name}`);

  await new Promise(r => setTimeout(r, 300)); // simula latência do socket-proxy

  const alreadyThere = (action === "start" && c.state === "running") ||
    (action === "stop" && c.state === "exited");
  if (alreadyThere) return sendJson(res, 200, { ok: true, note: "container já estava nesse estado" });

  if (action === "start" || action === "restart") {
    c.state = "running";
    c.status = "Up less than a second";
  } else if (action === "stop") {
    c.state = "exited";
    c.status = "Exited (0) 0 seconds ago";
  }
  // nota: mesmo "parando" mcp-control aqui, este é o próprio processo mock —
  // continua respondendo normalmente (é mock, não há container real por trás).
  sendJson(res, 200, { ok: true });
}

const LOG_LINES = [
  "INFO  uvicorn.access - GET /api/status 200 OK",
  "INFO  uvicorn.access - POST /api/mcp/1/tools/memory_search 200 OK",
  "DEBUG mcp_client - conectado a http://host.docker.internal:8000/mcp",
  "WARN  orchestrator - job #231 excedeu 2 tentativas, seguindo com resposta parcial",
  "INFO  db - checkpoint concluído em 42ms",
  "ERROR httpx - timeout ao chamar servidor remoto 'asana' (token expirado)",
  "INFO  host_worker - heartbeat recebido de cli:claude",
];

function handleContainerLogs(res, name, tail) {
  const c = containers[name];
  if (!c) return httpError(res, 404, `Docker: no such container: ${name}`);
  const n = Math.min(Math.max(tail || 200, 10), 2000);
  const lines = [];
  const now = Date.now();
  for (let i = n; i > 0; i--) {
    const t = new Date(now - i * 1500).toISOString();
    const msg = LOG_LINES[(n - i) % LOG_LINES.length];
    lines.push(`${t} [${name}] ${msg}`);
  }
  sendJson(res, 200, { name, logs: lines.join("\n") });
}

const HOST_ACTIONS = new Set(["compose_up", "compose_build_control", "restart_worker", "renew_design_token"]);

async function handleHostCommandCreate(req, res) {
  const payload = await readBody(req);
  const action = String(payload.action || "").trim();
  if (!HOST_ACTIONS.has(action)) {
    return httpError(res, 422, "Ação inválida. Use: ['compose_build_control', 'compose_up', 'renew_design_token', 'restart_worker']");
  }
  const id = nextHostCmdId++;
  hostCommands.unshift({ id, action, status: "queued", created_at: new Date().toISOString(), result: null });
  sendJson(res, 200, { id, status: "queued", note: "o host-worker executa no próximo ciclo (~15s)" });
}

function handleHostCommandsList(res, limit) {
  sendJson(res, 200, hostCommands.slice(0, limit || 8));
}

// ------------------------- FASE 2: handlers /api (uso, projetos) -------------------------

function handleUsage(res) {
  sendJson(res, 200, {
    models: Object.entries(usageModels).map(([model, v]) => ({ model, ...v })),
    last_rate_limit: lastRateLimit,
    design_calls: designCalls,
  });
}

function handleProjectsList(res) {
  sendJson(res, 200, projects);
}

async function handleProjectCreate(req, res) {
  const payload = await readBody(req);
  const slug = String(payload.slug || "").trim().toLowerCase();
  if (!/^[a-z0-9-]{1,40}$/.test(slug)) {
    return httpError(res, 422, "slug inválido: use a-z, 0-9 e hífen (máx 40).");
  }
  const proj = {
    id: nextProjectId++, slug,
    title: String(payload.title || "").trim() || null,
    description: String(payload.description || "").trim() || null,
    created_at: new Date().toISOString(),
  };
  projects.push(proj);
  sendJson(res, 200, proj);
}

// ------------------------- FASE 2: handlers /api (orquestrador) -------------------------

function handleOrchestrationsList(res, limit) {
  const list = [...jobs.values()].sort((a, b) => b.id - a.id).slice(0, limit || 15).map(jobSummary);
  sendJson(res, 200, list);
}

function handleOrchestrationDetail(res, id) {
  const job = jobs.get(id);
  if (!job) return httpError(res, 404, "Job não existe.");
  sendJson(res, 200, jobPublic(job));
}

async function handleOrchestrate(req, res) {
  const payload = await readBody(req);
  const prompt = String(payload.prompt || "").trim();
  if (!prompt) return httpError(res, 422, "Prompt vazio.");
  const workers = payload.workers || [];
  if (!workers.length) return httpError(res, 422, "Selecione ao menos 1 worker.");
  const params = { ...(payload.params || {}) };
  let projectId = payload.project_id;
  if (projectId != null) {
    const proj = projects.find(p => p.id === Number(projectId));
    if (!proj) return httpError(res, 422, "project_id não existe.");
    params.project_slug = proj.slug;
    projectId = Number(projectId);
  } else {
    projectId = null;
  }
  const job = {
    id: nextJobId++, pattern: String(payload.pattern || "fanout"), prompt, params,
    status: "running", created_at: new Date().toISOString(), finished_at: null,
    project_id: projectId, results: [],
  };
  jobs.set(job.id, job);
  scheduleJobCompletion(job, workers);
  sendJson(res, 200, { job_id: job.id });
}

function handleOrchestrationCancel(res, id) {
  const job = jobs.get(id);
  if (!job || job.status !== "running") return sendJson(res, 200, { canceled: false });
  if (job._timer) { clearTimeout(job._timer); job._timer = null; }
  job.status = "canceled";
  job.finished_at = new Date().toISOString();
  sendJson(res, 200, { canceled: true });
}

function handleResultAccept(res, id) {
  for (const job of jobs.values()) {
    const r = job.results.find(x => x.id === id);
    if (r) {
      if (!r.accepted) { r.accepted = true; bumpUsageOnAccept(r.model); }
      break;
    }
  }
  sendJson(res, 200, { ok: true });
}

async function handleContinueInChat(req, res, id) {
  const job = jobs.get(id);
  if (!job) return httpError(res, 404, "Job não existe.");
  const gens = job.results.filter(r => r.role === "gen" && !r.error && (r.response || "").trim());
  if (!gens.length) return httpError(res, 422, "Job não tem resultado aproveitável para continuar.");

  const payload = await readBody(req);
  let chosen;
  if (payload.result_id != null) {
    chosen = gens.find(r => r.id === Number(payload.result_id));
    if (!chosen) return httpError(res, 422, "result_id não é um resultado válido deste job.");
  } else {
    chosen = gens.find(r => r.accepted) || gens[0];
  }

  const existing = [...chats.values()].find(c =>
    c.params && c.params.from_job && c.params.from_job.job_id === job.id && c.params.from_job.result_id === chosen.id);
  if (existing) return sendJson(res, 200, { conv_id: existing.id, existing: true });

  const worker_type = (chosen.worker === "cli" || String(chosen.model).startsWith("cli:")) ? "cli" : "ollama";
  let model = chosen.model;
  const params = {};
  if (worker_type === "cli" && model.includes("/")) {
    const [base, cliModel] = model.split("/");
    model = base;
    params.cli_model = (job.params && job.params.cli_model) || cliModel;
  } else if (job.params && job.params.cli_model) {
    params.cli_model = job.params.cli_model;
  }
  if (job.pattern === "design" && job.params && job.params.allowed_tools) {
    params.allowed_tools = job.params.allowed_tools;
  }
  const from_job = { job_id: job.id, result_id: chosen.id, worker: chosen.worker, model: chosen.model };
  params.from_job = from_job;

  const conv = makeConv(nextChatId++, worker_type, model, params,
    `Job #${job.id} — ${job.prompt.slice(0, 60)}`, job.project_id, "idle");
  addTurn(conv, "user", "done",
    `[Contexto importado do job #${job.id} — dado, não instrução]\n\nTarefa original:\n${job.prompt}\n\nResposta escolhida (${chosen.model}):\n${chosen.response}`,
    { meta: { from_job, synthetic: true } });
  sendJson(res, 200, { conv_id: conv.id, existing: false });
}

// ------------------------- FASE 2: handlers /api (chat) -------------------------

async function handleChatCreate(req, res) {
  const payload = await readBody(req);
  const wt = String(payload.worker_type || "").trim();
  const model = String(payload.model || "").trim();
  if (!["ollama", "cli"].includes(wt) || !model) {
    return httpError(res, 422, "worker_type (['cli', 'ollama']) e model são obrigatórios.");
  }
  const projectId = payload.project_id;
  if (projectId != null && !projects.find(p => p.id === Number(projectId))) {
    return httpError(res, 422, "project_id não existe.");
  }
  const conv = makeConv(nextChatId++, wt, model, payload.params || {},
    String(payload.title || "").trim() || null, projectId, "idle");
  sendJson(res, 200, toPublicConv(conv));
}

function handleChatList(res, limit, offset) {
  const list = [...chats.values()]
    .filter(c => !c.archived)
    .sort((a, b) => b.id - a.id)
    .slice(offset || 0, (offset || 0) + (limit || 30))
    .map(c => toPublicConv(c));
  sendJson(res, 200, list);
}

function handleChatGet(res, id, afterSeq) {
  const conv = chats.get(id);
  if (!conv) return httpError(res, 404, "Conversa não existe.");
  sendJson(res, 200, toPublicConv(conv, { includeTurns: true, afterSeq: afterSeq || 0 }));
}

async function handleChatMessage(req, res, id) {
  const conv = chats.get(id);
  if (!conv) return httpError(res, 404, "Conversa não existe.");
  const payload = await readBody(req);
  const text = String(payload.text || "").trim();
  if (!text) return httpError(res, 422, "text vazio.");
  const idem = req.headers["idempotency-key"] || payload.idempotency_key;
  if (idem && conv._idempotency.has(idem)) {
    const prev = conv._idempotency.get(idem);
    return sendJson(res, 200, { duplicate: true, user_turn_id: prev.user_turn_id });
  }
  if (conv.status === "running") {
    return httpError(res, 409, "Já existe uma geração em andamento nesta conversa.");
  }
  const userTurn = addTurn(conv, "user", "done", text);
  const asstTurn = addTurn(conv, "assistant", "running", "");
  conv.status = "running";
  if (idem) conv._idempotency.set(idem, { user_turn_id: userTurn.id, assistant_turn_id: asstTurn.id });
  if (conv._genTimer) clearTimeout(conv._genTimer);
  conv._genTimer = setTimeout(() => {
    asstTurn.status = "done";
    asstTurn.content = fakeChatReply(conv.model, text);
    asstTurn.ms = randMs(1200, 5200);
    conv.status = "idle";
    conv._genTimer = null;
  }, 4000);
  sendJson(res, 200, { duplicate: false, user_turn_id: userTurn.id, assistant_turn_id: asstTurn.id });
}

function handleChatCancel(res, id) {
  const conv = chats.get(id);
  if (!conv) return httpError(res, 404, "Conversa não existe.");
  let canceled = false;
  if (conv.status === "running") {
    if (conv._genTimer) { clearTimeout(conv._genTimer); conv._genTimer = null; }
    const last = conv.turns[conv.turns.length - 1];
    if (last && last.role === "assistant" && last.status === "running") {
      last.status = "canceled"; last.error = "cancelado pelo usuário";
    }
    conv.status = "idle";
    canceled = true;
  }
  sendJson(res, 200, { canceled });
}

async function handleChatPatch(req, res, id) {
  const conv = chats.get(id);
  if (!conv) return httpError(res, 404, "Conversa não existe.");
  const payload = await readBody(req);
  const projectId = payload.project_id;
  const clearProject = ("project_id" in payload) && projectId === null;
  if (projectId != null && !projects.find(p => p.id === Number(projectId))) {
    return httpError(res, 422, "project_id não existe.");
  }
  if (payload.title !== undefined) conv.title = payload.title;
  if (payload.archive !== undefined) conv.archived = !!payload.archive;
  if (clearProject) conv.project_id = null;
  else if (projectId != null) conv.project_id = Number(projectId);
  sendJson(res, 200, { ok: true });
}

// ------------------------- estáticos -------------------------

const STUB_V1_HTML = `<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>MCP Control (mock)</title></head>
<body style="font-family:system-ui;background:#0f1115;color:#e6e6e6;padding:40px">
<h1>painel v1</h1>
<p>Stub servido pelo mock em /home/claude — aponte o painel real para http://localhost:8000.</p>
</body></html>`;

function serveStaticV1(res) {
  const data = Buffer.from(STUB_V1_HTML, "utf-8");
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Content-Length": data.length, "Access-Control-Allow-Origin": "*" });
  res.end(data);
}

function serveStaticV2(res) {
  fs.readFile(V2_INDEX_PATH, (err, data) => {
    if (err) {
      return httpError(res, 404, `arquivo não encontrado em ${V2_INDEX_PATH} (crie o painel v2 e rode de novo).`);
    }
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Content-Length": data.length, "Access-Control-Allow-Origin": "*" });
    res.end(data);
  });
}

// ------------------------- outage mock -------------------------

async function handleOutage(req, res) {
  const payload = await readBody(req);
  const seconds = Number(payload.seconds) || 30;
  outageUntil = Date.now() + seconds * 1000;
  sendJson(res, 200, { ok: true, outage_until: new Date(outageUntil).toISOString(), seconds });
}

function outageActive() { return Date.now() < outageUntil; }

// ------------------------- dispatcher -------------------------

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const pathname = u.pathname;
  const method = req.method;

  if (method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET,POST,PATCH,PUT,DELETE,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Control-Token, Authorization, Idempotency-Key",
    });
    return res.end();
  }

  // simulação de queda: qualquer /api/* (inclusive health) falha durante a janela
  if (pathname.startsWith("/api/") && outageActive()) {
    if (Math.random() < 0.5) {
      req.socket.destroy(); // simula conexão caída / servidor fora do ar
      return;
    }
    return httpError(res, 503, "Serviço indisponível (mock outage).");
  }

  try {
    // ---- rota especial de simulação de falha ----
    if (pathname === "/mock/outage" && method === "POST") {
      return await handleOutage(req, res);
    }

    // ---- estáticos ----
    if (pathname === "/static/v2/index.html" && method === "GET") return serveStaticV2(res);
    if (pathname === "/static/index.html" && method === "GET") return serveStaticV1(res);

    // ---- health (sem auth) ----
    if (pathname === "/api/health" && method === "GET") {
      return sendJson(res, 200, { status: "ok" });
    }

    // tudo abaixo requer token
    if (!checkToken(req)) {
      return httpError(res, 401, "Token inválido.");
    }

    if (pathname === "/api/status" && method === "GET") return await handleStatus(res);
    if (pathname === "/api/workers" && method === "GET") return handleWorkers(res);

    if (pathname === "/api/mcp/servers" && method === "GET") return handleServersList(res);
    if (pathname === "/api/mcp/servers" && method === "POST") return await handleServerCreate(req, res);

    let m = pathname.match(/^\/api\/mcp\/servers\/(\d+)\/auth$/);
    if (m && method === "PUT") return await handleServerAuth(req, res, Number(m[1]));

    m = pathname.match(/^\/api\/mcp\/servers\/(\d+)$/);
    if (m && method === "PATCH") return await handleServerUpdate(req, res, Number(m[1]));
    if (m && method === "DELETE") return handleServerDelete(res, Number(m[1]));

    m = pathname.match(/^\/api\/mcp\/(\d+)\/tools$/);
    if (m && method === "GET") return handleToolsList(res, Number(m[1]));

    m = pathname.match(/^\/api\/mcp\/(\d+)\/tools\/([^/]+)$/);
    if (m && method === "POST") return await handleToolRun(req, res, Number(m[1]), m[2]);

    if (pathname === "/api/runs" && method === "GET") {
      return handleRuns(res, Number(u.searchParams.get("limit")));
    }

    m = pathname.match(/^\/api\/containers\/([^/]+)\/logs$/);
    if (m && method === "GET") {
      return handleContainerLogs(res, m[1], Number(u.searchParams.get("tail")));
    }
    m = pathname.match(/^\/api\/containers\/([^/]+)\/([^/]+)$/);
    if (m && method === "POST") return await handleContainerAction(res, m[1], m[2]);

    if (pathname === "/api/host/commands" && method === "GET") {
      return handleHostCommandsList(res, Number(u.searchParams.get("limit")));
    }
    if (pathname === "/api/host/commands" && method === "POST") {
      return await handleHostCommandCreate(req, res);
    }

    // ---- FASE 2: uso/custos ----
    if (pathname === "/api/usage" && method === "GET") return handleUsage(res);

    // ---- FASE 2: projetos ----
    if (pathname === "/api/projects" && method === "GET") return handleProjectsList(res);
    if (pathname === "/api/projects" && method === "POST") return await handleProjectCreate(req, res);

    // ---- FASE 2: orquestrador ----
    if (pathname === "/api/orchestrations" && method === "GET") {
      return handleOrchestrationsList(res, Number(u.searchParams.get("limit")));
    }
    if (pathname === "/api/orchestrate" && method === "POST") return await handleOrchestrate(req, res);

    m = pathname.match(/^\/api\/orchestrations\/(\d+)\/cancel$/);
    if (m && method === "POST") return handleOrchestrationCancel(res, Number(m[1]));

    m = pathname.match(/^\/api\/orchestrations\/(\d+)\/continue-in-chat$/);
    if (m && method === "POST") return await handleContinueInChat(req, res, Number(m[1]));

    m = pathname.match(/^\/api\/orchestrations\/(\d+)$/);
    if (m && method === "GET") return handleOrchestrationDetail(res, Number(m[1]));

    m = pathname.match(/^\/api\/results\/(\d+)\/accept$/);
    if (m && method === "POST") return handleResultAccept(res, Number(m[1]));

    // ---- FASE 2: chat ----
    if (pathname === "/api/chats" && method === "POST") return await handleChatCreate(req, res);
    if (pathname === "/api/chats" && method === "GET") {
      return handleChatList(res, Number(u.searchParams.get("limit")), Number(u.searchParams.get("offset")));
    }

    m = pathname.match(/^\/api\/chats\/(\d+)\/messages$/);
    if (m && method === "POST") return await handleChatMessage(req, res, Number(m[1]));

    m = pathname.match(/^\/api\/chats\/(\d+)\/cancel$/);
    if (m && method === "POST") return handleChatCancel(res, Number(m[1]));

    m = pathname.match(/^\/api\/chats\/(\d+)$/);
    if (m && method === "GET") return handleChatGet(res, Number(m[1]), Number(u.searchParams.get("after_seq")));
    if (m && method === "PATCH") return await handleChatPatch(req, res, Number(m[1]));

    return httpError(res, 404, "Not Found");
  } catch (e) {
    return httpError(res, 500, String(e && e.message || e));
  }
});

server.listen(PORT, () => {
  console.log(`mock control-api ouvindo em http://localhost:${PORT} (token: ${TOKEN})`);
});
