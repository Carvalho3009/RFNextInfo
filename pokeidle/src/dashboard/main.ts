import { commandInstance, readToken, saveToken, subscribeInstances } from "./api.js";
import { demoInstances } from "./demo-data.js";
import type { InstanceStatus, MetricSample } from "./types.js";

const root = document.querySelector<HTMLDivElement>("#root");
if (!root) throw new Error("Elemento raiz não encontrado");

const demoMode = new URLSearchParams(location.search).has("demo");
let instances: InstanceStatus[] = demoMode ? demoInstances : [];
let selectedId: string | null = demoMode ? "principal" : null;
let drawerOpen = false;
let modal: "token" | "info" | null = null;
let busy = false;
let message = demoMode ? "Modo demonstração: dados ilustrativos, sem cliente do jogo." : "Conectando ao supervisor…";
let unsubscribe: (() => void) | null = null;
let reconnectTimer: number | null = null;

function render(): void {
  const selected = instances.find((instance) => instance.id === selectedId) ?? null;
  const supervisorHealthy = instances.some((instance) => instance.running);
  root.innerHTML = `
    <div class="app-shell">
      <header class="topbar">
        <button class="icon-button topbar__menu" data-ui="open-drawer" type="button" aria-label="Abrir instâncias">${icon("menu", 24)}</button>
        <a class="brand" href="/" aria-label="Poke Idle Supervisor">Poke Idle Supervisor</a>
        <div class="supervisor-health ${supervisorHealthy ? "supervisor-health--ok" : ""}"><span></span>${supervisorHealthy ? "Supervisor saudável" : "Supervisor aguardando"}</div>
        <div class="topbar__actions">
          <button class="button button--secondary" data-ui="new-instance" type="button">${icon("plus", 19)}Nova instância</button>
          <button class="icon-button" data-ui="settings" type="button" aria-label="Configurar acesso">${icon("settings", 21)}</button>
        </div>
      </header>
      <div class="workspace">
        ${sidebarTemplate()}
        ${drawerOpen ? '<button class="drawer-backdrop" data-ui="close-drawer" type="button" aria-label="Fechar menu"></button>' : ""}
        ${selected ? detailTemplate(selected) : emptyTemplate()}
      </div>
      <div class="connection-message" role="status">${escapeHtml(message)}</div>
      <footer class="safety-footer">
        ${icon("shield", 24)}<strong>Proteções ativas:</strong><span>sem Modo Soneca</span><i></i><span>sem chat</span><i></i><span>sem PvP</span><i></i><span>sem diamantes</span><i></i><span>compras não implementadas</span>
      </footer>
      ${modal === "token" ? tokenDialogTemplate() : ""}
      ${modal === "info" ? infoDialogTemplate() : ""}
    </div>`;
  bindInteractions();
}

function sidebarTemplate(): string {
  const rows = instances.map((instance) => `
    <button type="button" data-instance="${escapeHtml(instance.id)}" class="instance-row ${selectedId === instance.id ? "instance-row--selected" : ""}">
      <span class="status-dot status-dot--${instance.tone}" aria-hidden="true"></span>
      <span class="instance-row__content">
        <span class="instance-row__top"><strong>${escapeHtml(instance.id)}</strong><span>${relativeTime(instance.lastHeartbeat)}</span></span>
        <span class="instance-row__state text--${instance.tone}">${statusLabel(instance)} / <code>${instance.state}</code></span>
        <span class="instance-row__heartbeat">Último heartbeat: ${relativeTime(instance.lastHeartbeat)}</span>
      </span>
    </button>`).join("");
  const attention = instances.some((instance) => instance.tone === "attention" || instance.tone === "error");
  return `
    <aside class="sidebar ${drawerOpen ? "sidebar--open" : ""}" aria-label="Instâncias">
      <div class="sidebar__heading"><h2>Instâncias</h2><button class="icon-button sidebar__close" data-ui="close-drawer" type="button" aria-label="Fechar instâncias">${icon("x", 20)}</button></div>
      <div class="instance-list">${rows}</div>
      ${attention ? `<div class="intervention-callout">${icon("alert", 19)}<span><strong>Intervenção necessária</strong><small>Abra a instância em atenção para ver o motivo.</small></span>${icon("chevron", 18)}</div>` : ""}
      <button class="sidebar__settings" data-ui="settings" type="button">${icon("settings", 20)}Configuração</button>
    </aside>`;
}

function detailTemplate(instance: InstanceStatus): string {
  const metric = instance.latestMetric;
  return `
    <main class="instance-detail">
      <header class="instance-header">
        <div class="instance-identity"><h1>${escapeHtml(instance.id)}</h1><span>${icon("user", 18)}${escapeHtml(instance.accountLabel)}</span><i></i><span>${icon("monitor", 18)}${escapeHtml(instance.environment)}</span></div>
        <div class="instance-actions">
          ${instance.running
            ? `<button class="button button--danger" data-command="stop" type="button" ${busy ? "disabled" : ""}>${icon("square", 16)}Parar</button>`
            : `<button class="button button--primary" data-command="start" type="button" ${busy ? "disabled" : ""}>${icon("play", 17)}Iniciar</button>`}
          <button class="button button--secondary" data-command="restart" type="button" ${busy ? "disabled" : ""}>${icon("rotate", 18)}Reiniciar</button>
          <button class="icon-button" type="button" aria-label="Mais opções" disabled>${icon("more", 20)}</button>
        </div>
      </header>
      <section class="status-band status-band--${instance.tone}">
        <div class="status-band__state"><code>${instance.state}</code><span>${escapeHtml(instance.reason ?? (instance.state === "MONITOR_COMBAT" ? "Cliente oficial conectado" : "Estado observado pelo supervisor"))}</span></div>
        <span class="heartbeat-mark">${icon("activity", 72)}</span>
        ${statusMetric("Uptime", uptime(instance.startedAt))}
        ${statusMetric("Chromium RSS", formatMetric(metric?.chromiumRssMb, " MB"))}
        ${statusMetric("Node RSS", formatMetric(metric?.nodeRssMb, " MB"))}
        ${statusMetric("CPU", metric?.chromiumCpuPercent == null ? "—" : `${metric.chromiumCpuPercent}%`)}
        ${statusMetric("Heartbeat", relativeTime(instance.lastHeartbeat))}
      </section>
      <div class="operational-grid">${combatTemplate(instance)}${resourcesTemplate(instance.metrics)}</div>
      ${activityTemplate(instance)}
    </main>`;
}

function statusMetric(label: string, value: string): string {
  return `<div class="status-metric"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function combatTemplate(instance: InstanceStatus): string {
  const value = instance.observation;
  const hp = value?.hpPercent;
  return `<section class="panel combat-panel" aria-labelledby="combat-title">
    <div class="panel__heading"><h3 id="combat-title">Combate</h3></div>
    ${combatRow("activity", "Hunt", triState(value?.huntActive, "configurada", "inativa"))}
    ${combatRow("user", "Personagem", triState(value?.characterPresent, "saudável", "não localizado"))}
    ${combatRow("heart", "HP", hp == null ? "—" : `${hp}%`)}
    ${combatRow("flask", "Auto-Potion", triState(value?.autoPotionEnabled, "ativo", "inativo"))}
    ${combatRow("cross", "Auto-Revive", triState(value?.autoReviveEnabled, "ativo", "inativo"))}
    <div class="hp-area"><span>HP atual</span><div class="hp-track" role="progressbar" aria-label="HP atual" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${hp ?? 0}"><i style="width:${hp ?? 0}%"></i><strong>${hp == null ? "—" : `${hp}%`}</strong></div></div>
  </section>`;
}

function combatRow(iconName: IconName, label: string, value: string): string {
  const healthy = ["configurada", "saudável", "ativo"].includes(value);
  return `<div class="combat-row"><span class="combat-row__icon">${icon(iconName, 21)}</span><span>${label}:</span><strong class="${healthy ? "text--healthy" : ""}">${escapeHtml(value)}</strong></div>`;
}

function resourcesTemplate(samples: MetricSample[]): string {
  const latest = samples.at(-1);
  const points = chartPoints(samples);
  const chart = samples.length > 1 ? `<svg class="resource-chart" viewBox="0 0 640 220" role="img" aria-label="Histórico de CPU e memória">
    <g class="chart-grid">${[25,65,105,145,185].map((y) => `<line x1="42" y1="${y}" x2="614" y2="${y}"></line>`).join("")}${[42,185,328,471,614].map((x) => `<line x1="${x}" y1="18" x2="${x}" y2="185"></line>`).join("")}</g>
    <line class="chart-axis" x1="42" y1="185" x2="614" y2="185"></line><polyline class="chart-line chart-line--memory" points="${points.memory}"></polyline><polyline class="chart-line chart-line--cpu" points="${points.cpu}"></polyline>
    <text x="42" y="208">${clock(samples[0]?.at ?? null, true)}</text><text x="560" y="208">${clock(latest?.at ?? null, true)}</text></svg>` : '<div class="chart-empty">Aguardando amostras do processo.</div>';
  return `<section class="panel resources-panel" aria-labelledby="resources-title">
    <div class="panel__heading"><h3 id="resources-title">Recursos</h3><span>Dados de monitoramento</span></div>
    <div class="chart-legend" aria-hidden="true"><span><i class="legend-line legend-line--cpu"></i>CPU (%)</span><span><i class="legend-line legend-line--memory"></i>Memória (MB)</span></div>
    <div class="chart-wrap">${chart}</div>
    <div class="resource-summary"><div><span>CPU atual</span><strong class="text--healthy">${formatMetric(latest?.chromiumCpuPercent, "%")}</strong></div><div><span>Memória Chromium</span><strong class="text--info">${formatMetric(latest?.chromiumRssMb, " MB")}</strong></div><div><span>Heap JS</span><strong>${formatMetric(latest?.jsHeapMb, " MB")}</strong></div></div>
  </section>`;
}

function activityTemplate(instance: InstanceStatus): string {
  const rows: Array<[string | null, string, string]> = [
    [instance.lastHeartbeat, "Heartbeat confirmado", instance.lastHeartbeat ? "OK" : "AGUARDA"],
    [instance.lastHeartbeat, instance.observation?.huntActive ? "Hunt permanece ativa" : "Hunt não confirmada", instance.observation?.huntActive ? "OK" : "ATENÇÃO"],
    [instance.lastHeartbeat, instance.observation?.connected ? "Conexão do cliente saudável" : "Cliente desconectado", instance.observation?.connected ? "OK" : "FALHA"],
    [instance.startedAt, instance.running ? "Chromium iniciado" : "Instância parada", "INFO"],
  ];
  return `<section class="panel activity-panel" aria-labelledby="activity-title"><div class="panel__heading"><h3 id="activity-title">Atividade recente</h3></div><div class="activity-table" role="table"><div class="activity-row activity-row--header" role="row"><span>Hora</span><span>Evento</span><span>Status</span></div>${rows.map(([time,event,status]) => `<div class="activity-row" role="row"><span><i class="event-dot event-dot--${status.toLowerCase()}"></i>${clock(time)}</span><span>${escapeHtml(event)}</span><code>${status}</code></div>`).join("")}</div></section>`;
}

function tokenDialogTemplate(): string {
  return `<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="token-title"><button class="icon-button modal__close" data-ui="close-modal" type="button" aria-label="Fechar">${icon("x", 19)}</button><h2 id="token-title">Acesso ao supervisor</h2><p>O token fica apenas nesta aba e nunca é enviado aos logs.</p><label>Token do dashboard<input id="dashboard-token" type="password" autocomplete="off" value="${escapeHtml(readToken())}"></label><button class="button button--primary" data-ui="save-token" type="button">Salvar nesta aba</button></section></div>`;
}

function infoDialogTemplate(): string {
  return `<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="instance-title"><button class="icon-button modal__close" data-ui="close-modal" type="button" aria-label="Fechar">${icon("x",19)}</button><h2 id="instance-title">Adicionar instância</h2><p>Por segurança, contas e perfis são declarados em <code>config.yaml</code>. O dashboard controla todas as instâncias já cadastradas.</p><button class="button button--secondary" data-ui="close-modal" type="button">Entendi</button></section></div>`;
}

function emptyTemplate(): string {
  return `<main class="empty-state">${icon("shield",42)}<h1>Nenhuma instância configurada</h1><p>Copie o arquivo de exemplo e adicione uma instância antes de iniciar o supervisor.</p></main>`;
}

function bindInteractions(): void {
  root.querySelectorAll<HTMLElement>("[data-instance]").forEach((element) => element.addEventListener("click", () => { selectedId = element.dataset.instance ?? null; drawerOpen = false; render(); }));
  root.querySelectorAll<HTMLElement>("[data-command]").forEach((element) => element.addEventListener("click", () => void runCommand(element.dataset.command as "start" | "stop" | "restart")));
  root.querySelectorAll<HTMLElement>('[data-ui="open-drawer"]').forEach((element) => element.addEventListener("click", () => { drawerOpen = true; render(); }));
  root.querySelectorAll<HTMLElement>('[data-ui="close-drawer"]').forEach((element) => element.addEventListener("click", () => { drawerOpen = false; render(); }));
  root.querySelectorAll<HTMLElement>('[data-ui="settings"]').forEach((element) => element.addEventListener("click", () => { modal = "token"; render(); }));
  root.querySelectorAll<HTMLElement>('[data-ui="new-instance"]').forEach((element) => element.addEventListener("click", () => { modal = "info"; render(); }));
  root.querySelectorAll<HTMLElement>('[data-ui="close-modal"]').forEach((element) => element.addEventListener("click", () => { modal = null; render(); }));
  root.querySelector<HTMLElement>('[data-ui="save-token"]')?.addEventListener("click", () => { saveToken(root.querySelector<HTMLInputElement>("#dashboard-token")?.value.trim() ?? ""); modal = null; connectToSupervisor(); });
}

async function runCommand(command: "start" | "stop" | "restart"): Promise<void> {
  const selected = instances.find((instance) => instance.id === selectedId);
  if (!selected) return;
  if (demoMode) {
    instances = instances.map((instance) => instance.id === selected.id ? demoTransition(instance, command) : instance);
    message = `Comando ${command} simulado no modo de demonstração.`;
    render();
    return;
  }
  if (!readToken()) { modal = "token"; message = "Informe o token antes de enviar comandos."; render(); return; }
  busy = true; render();
  try { await commandInstance(selected.id, command); message = `Comando ${command} aceito para ${selected.id}.`; }
  catch (error) { message = error instanceof Error ? error.message : "Falha ao enviar comando"; modal = "token"; }
  finally { busy = false; render(); }
}

function demoTransition(instance: InstanceStatus, command: "start" | "stop" | "restart"): InstanceStatus {
  if (command === "stop") return { ...instance, running: false, state: "SAFE_STOP", tone: "stopped", reason: "Parada solicitada pelo operador" };
  return { ...instance, running: true, state: "BOOT", tone: "attention", reason: command === "restart" ? "Reiniciando worker" : "Inicializando worker" };
}

function chartPoints(samples: MetricSample[]): { cpu: string; memory: string } {
  if (!samples.length) return { cpu: "", memory: "" };
  const maxIndex = Math.max(samples.length - 1, 1);
  const memoryValues = samples.map((sample) => sample.chromiumRssMb ?? 0);
  const memoryMin = Math.min(...memoryValues) - 10;
  const memoryMax = Math.max(...memoryValues) + 10;
  const coordinates = (selector: (sample: MetricSample) => number, min: number, max: number): string => samples.map((sample,index) => `${(42 + (index/maxIndex)*572).toFixed(1)},${(185 - ((selector(sample)-min)/Math.max(max-min,1))*145).toFixed(1)}`).join(" ");
  return { cpu: coordinates((sample) => sample.chromiumCpuPercent ?? 0, 0, 10), memory: coordinates((sample) => sample.chromiumRssMb ?? 0, memoryMin, memoryMax) };
}

function statusLabel(instance: InstanceStatus): string { return instance.tone === "healthy" ? "Online" : instance.tone === "stopped" ? "Parada" : instance.tone === "error" ? "Falha" : "Atenção"; }
function triState(value: boolean | null | undefined, yes: string, no: string): string { return value == null ? "—" : value ? yes : no; }
function uptime(value: string | null): string { if (!value) return "—"; const minutes = Math.max(0,Math.floor((Date.now()-Date.parse(value))/60000)); return `${Math.floor(minutes/60)}h ${minutes%60}m`; }
function relativeTime(value: string | null): string { if (!value) return "nunca"; const seconds=Math.max(0,Math.floor((Date.now()-Date.parse(value))/1000)); if(seconds<10)return "agora"; if(seconds<60)return `${seconds}s atrás`; const minutes=Math.floor(seconds/60); return minutes<60?`${minutes}m atrás`:`${Math.floor(minutes/60)}h atrás`; }
function clock(value: string | null, short=false): string { return value ? new Date(value).toLocaleTimeString("pt-BR", short ? {hour:"2-digit",minute:"2-digit"} : undefined) : "—"; }
function formatMetric(value: number | null | undefined, suffix: string): string { return value == null ? "—" : `${value.toLocaleString("pt-BR",{maximumFractionDigits:1})}${suffix}`; }
function escapeHtml(value: string): string { return value.replace(/[&<>'"]/g,(character)=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[character] ?? character); }

type IconName = "menu"|"plus"|"settings"|"shield"|"user"|"monitor"|"square"|"rotate"|"play"|"more"|"activity"|"heart"|"flask"|"cross"|"alert"|"chevron"|"x";
const ICON_PATHS: Record<IconName,string> = {
  menu:'<path d="M4 6h16M4 12h16M4 18h16"/>', plus:'<path d="M12 5v14M5 12h14"/>', settings:'<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/>',
  shield:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>', user:'<circle cx="12" cy="8" r="4"/><path d="M4 22a8 8 0 0 1 16 0"/>', monitor:'<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>', square:'<rect x="5" y="5" width="14" height="14" rx="1"/>', rotate:'<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>', play:'<path d="m8 5 11 7-11 7Z"/>', more:'<circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>', activity:'<path d="M3 12h4l2-7 4 14 2-7h6"/>', heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1.1L12 21l7.8-7.5 1.1-1.1a5.5 5.5 0 0 0-.1-7.8Z"/>', flask:'<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M7 16h10"/>', cross:'<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>', alert:'<path d="M10.3 3.7 2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>', chevron:'<path d="m9 18 6-6-6-6"/>', x:'<path d="M18 6 6 18M6 6l12 12"/>'
};
function icon(name: IconName,size: number): string { return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name]}</svg>`; }

render();
if (!demoMode) connectToSupervisor();

function connectToSupervisor(): void {
  unsubscribe?.();
  unsubscribe = null;
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
  reconnectTimer = null;
  if (!readToken()) {
    instances = [];
    selectedId = null;
    message = "Informe o token do dashboard em Configuração para carregar as instâncias.";
    render();
    return;
  }
  message = "Conectando ao supervisor…";
  render();
  unsubscribe = subscribeInstances(
    (next) => {
      instances = next;
      if (!selectedId || !next.some((item) => item.id === selectedId)) selectedId = next[0]?.id ?? null;
      message = "Supervisor conectado";
      render();
    },
    (error) => {
      message = error.message;
      render();
      reconnectTimer = window.setTimeout(() => connectToSupervisor(), 5_000);
    },
  );
}
