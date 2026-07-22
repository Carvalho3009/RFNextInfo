# LEVANTAMENTO F6 (SPEC-014) — Design do Painel MCP v2
**Data:** 18/07/2026 · **Processo:** brief único → fanout cli:claude/claude-fable-5 (job #233) × cli:codex/gpt-5.6-sol (job #234) via MCP público → comparação e consolidação pelo fable (Cowork) · **Projeto stack:** `painel-v2`
**Identidade aplicada:** Karvalho (Codex, `projects/rooc-americas/mockup`) — coal `#070909`, bone `#f4f2eb`, gold `#d4a64d`, acid `#a8ff16`, coral `#ff6547`, water `#63b9f3`, violet `#8a6ed6`, muted `#a7a6a0`, panel `#0e1211`; Bahnschrift Condensed (display) + Segoe UI/Inter (body); molduras gold com cantos ornamentais 12×12.

---

## 1. Convergências (consenso — entram direto na spec consolidada)

Os dois agentes, de forma independente, propuseram praticamente o mesmo esqueleto:

1. **Conceito idêntico em essência:** "ornamento na casca, dado nu" (fable) ≈ "console editorial operacional" (sol). Identidade Karvalho no chrome (navegação, cabeçalhos, modais, estados críticos); zero ornamento em linhas de tabela e dados densos.
2. **Sidebar lateral esquerda fixa** ~216–220px, colapsável para 64px, display uppercase, item ativo em acid.
3. **Barra de sistema global no topo** (40–48px): VRAM + fila `aguardando_vram`, fila de recursos §3.6, estado de conexão/stale, sino com histórico de notificações.
4. **Promoções:** Workers, Uso/custos e Grill Me viram abas próprias; containers/host saem da telemetria para uma zona de operação demarcada.
5. **Hash-routing + deep-links + breadcrumbs** em telas de detalhe, sem tocar nas rotas do control-api.
6. **Mapeamento de cores idêntico:** ok/live = acid (nunca como preenchimento de área grande), warn = gold **sempre com ícone ▲** (gold também é estrutura), err/destrutivo = coral, info/focus = water, batch/categoria = violet. Barras mantêm thresholds 75/90%.
7. **Tipografia:** display condensado só em títulos/labels/botões/th/métricas; body para texto; **novo token mono** para números/IDs/custos. Escala 4px (4/8/12/16/24/32/48), raio 2px, moldura padrão gold .45 com cantos ornamentais restritos a cabeçalho/painel prioritário/modal crítico/relatório do Grill.
8. **Modais próprios substituem alert/confirm/prompt**, com 3 níveis de ação destrutiva: reversível (inline/undo) → disruptiva (modal com consequência) → crítica (digitar o nome do alvo; ex.: parar o container do próprio painel). Comandos de host mostram o comando literal antes do OK.
9. **Estados completos:** skeleton, empty com CTA, error com retry, **stale honesto** ("dados de Xs atrás", dado envelhece visível, nunca some; sparkline não continua linha falsa), offline com reconexão.
10. **Toast com histórico** em drawer (resolve "toasts somem").
11. **Fila §3.6 sempre visível:** job/conversa em `aguardando_recurso` mostra recurso, dono (clicável), posição e prioridade — nunca trava em silêncio.
12. **Workers §3.5 completo:** toggle, chips allow (acid)/block (coral ⊘)/herdado (muted), limites (concorrência, tokens/job, tokens/dia, keep_alive) com edição inline, tooltip de temperatura com faixas, auditoria versionada com diff e drawer de histórico, matriz papéis×worker por projeto com célula de 3 estados e aplicação em lote.
13. **Endpoints órfãos ganham UI:** auth OAuth de servidor MCP (`PUT .../auth`), editar URL (`PATCH`), descrição de projeto (`POST /api/projects`), `GET /api/health` na barra global.
14. **Login sem expor o caminho do token.**
15. **Acessibilidade:** números de contraste praticamente idênticos nos dois (bone ~17,8:1 AAA; acid ~16:1; muted ~8,2:1 — melhora o débito atual; coral ~6,8:1 AA); estado nunca só por cor; focus water 2px; aria-modal/switch/progressbar; reduced-motion. Alerta do fable: **borda gold .45 reprova 3:1 para componente interativo → usar .65 em inputs/toggles/células clicáveis**.
16. **Direção de mockup recomendada pelos dois: a híbrida/equilibrada** (identidade no chrome, densidade no miolo), com uma variante "ops compacta" e uma "editorial plena" como alternativas.

## 2. Divergências (decisão do owner)

| # | Ponto | fable (#233) | gpt-5.6-sol (#234) | Recomendação do revisor |
|---|---|---|---|---|
| D1 | **Onde vivem containers + comandos de host** | Status, zona "OPERAÇÕES" demarcada em coral | Tools › "Runtime e host" (Status vira 100% observacional) | **sol** — separar observar de agir é mais seguro; Status continua respondendo "está saudável?" e a barra global denuncia incidente |
| D2 | **Ordem das abas** | Status, Workers, **Orquestrador, Chat**, Grill, Tools, Uso, Instruções (frequência de uso) | Status, Workers, **Tools, Orquestrador**, Chat, Grill, Uso, Instruções (ordem F6 da spec) | **fable** — Orquestrador/Chat são o uso diário; Tools é ocasional |
| D3 | **Layout da aba Workers** | Grid de cards (2 col) + vista Matriz | **Lista mestre 300px + detalhe** em 4 seções + subvista Matriz | **sol** — master-detail escala melhor com §3.5 completo (papéis+limites+auditoria por worker) e dá lugar natural ao diff "salvar nova versão" |
| D4 | **Grill Me** | Coluna única centrada 720px (leitura) | Coluna principal + **resumo lateral 280px** com totais/pendências | **sol** — o resumo lateral responde "quanto falta para finalizar" sem rolar; ações: manter cores do fable (defender=gold, risco=coral) por semântica de perigo |
| D5 | **Ordem de migração** | Instruções → Status → Workers → Uso → Tools → Orquestrador → Chat → Grill | **Status** → Tools → Workers → Orquestrador → Uso → Chat → Grill → Instruções | **híbrida:** casca/tokens → **Instruções** (risco zero, valida casca) → **Status** → **Tools** (tira o perigo do lugar errado cedo) → Workers → Uso → Orquestrador → Chat → Grill |
| D6 | **Sparklines** | Monocromática acid, muda p/ gold/coral ao cruzar threshold | Uma cor por métrica (CPU acid, GPU water, VRAM gold, disco violet) | **fable** — cor = estado (não identidade da métrica) mantém o semáforo coerente no painel inteiro; rótulo distingue a métrica |
| D7 | **Badges de estado** | Nunca preencher com acid; ponto 6px + texto | Badges preenchidos (acid/gold/coral com texto coal) | **fable** como regra geral (acid escasso); preenchido só em badge crítico (ERRO/ENCERRADO), seguindo o próprio risco nº1 apontado pelo sol |
| D8 | **Instruções** | Coluna única + TOC | Lista de escopos + editor com **preview lado a lado** + proteção contra perda | **sol simplificado** — editor+preview+guard de alterações não salvas; SEM lista de escopos (o backend só tem get/set de um documento — a lista extrapola a API atual) |
| D9 | **Uso/custos** | 4 stat tiles + sparkline 30d + tabela por modelo e por projeto | Filtros ricos + rótulos **REAL / ESTIMADO / SEM TARIFA** | **fusão** — tiles do fable + honestidade de custo do sol ("sem tarifa" nunca vira R$ 0) |
| D10 | **Atalhos** | Alt+1..8, `/`, `f` (fila), Esc | Só `/`, Ctrl+Enter, Esc, `?` | **sol na v1** (mínimo previsível) + `?` de ajuda; Alt+1..8 fica para depois do uso real |

## 3. Riscos honestos levantados (os dois concordam)

Gold acumulando marca+warning (mitigar com ícone obrigatório); acid cansativo em 8h de sala escura (racionar); Bahnschrift condensed ruim para varredura de tabela e refém do Windows (fallback Arial Narrow degrada); coexistência visual v1/v2 durante a migração; fila global duplicando dados do Status (fonte única no cliente); complexidade nova em JS vanilla (risco de recriar o espaguete de estilos inline em forma de estado).

## 4. Próximos passos

1. Owner bate o martelo nas divergências D1–D10 (recomendações acima).
2. Consolidar spec de design F6 (documento próprio, formato proposta doc 09) com as decisões.
3. Mockups navegáveis (2–3 direções: equilibrada recomendada + ops compacta + editorial plena) cobrindo as 8 abas — aprovação antes de qualquer implementação.
4. Implementação aba por aba na ordem D5, rotas do control-api intocadas.
