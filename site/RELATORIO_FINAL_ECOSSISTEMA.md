# Relatório Final — Auditoria do Ecossistema Karvalho

**Data:** 2026-07-22
**Escopo:** auditoria profunda com acesso completo a `Site`, `K:\MCP` e `RF NEXt`, consolidando e corrigindo os dois relatórios anteriores (`RELATORIO_AUDITORIA_KARVALHO.md` e `AUDITORIA_DOC_CONSOLIDADO.md`).
**Método:** 3 agentes Opus/Sonnet em paralelo (infra MCP, ecossistema RF Next, projetos satélites) + verificação final Fable dos achados críticos contra os arquivos.

---

## 1) Correções sobre os relatórios anteriores

Com acesso ao código real, dois achados anteriores mudam:

1. **MCP Vision É usado — a suspeita de "variável morta" caiu.** O `server.py` real (1054 linhas, em `RF NEXt`) usa `MCP_VISION_URL/TOKEN` como **OCR primário** de capturas de mercado (POST da imagem com header `X-RFNext-Vision-Token`, timeout 75s), com fallback automático para tesseract local embutido na imagem. O diagrama do doc do Site estava certo; o que nos enganou foi a cópia defasada em `Site\projects\rf-next` (136 linhas, sem nada disso). Ressalva: como `MCP_VISION_TOKEN` cai para vazio sem `.env`, hoje o caminho MCP está **inerte silenciosamente** e tudo roda em tesseract.
2. **`Site\projects\rf-next` não é "fonte alternativa" nem "alvo de deploy" funcional — é peso morto.** Snapshot antigo do app + uma cópia de `craft.html` que nunca chega ao container (ver §2). Recomendação: remover a pasta (ou reduzi-la a um README apontando para as fontes reais).

Confirmado com o Caddyfile em mãos: o gateway **sobrescreve** `X-Karvalho-User` com `X-Authentik-Username` e **remove** `Cf-Access-Authenticated-User-Email` (linhas 39-40) — impersonação via gateway está bloqueada. Risco residual: dentro da rede Docker, requisição direta a `rfnext:80` com `Host: rfnext` ganha o usuário `local` (exige comprometer outro container antes).

## 2) A cadeia de deploy do RF Next, explicada (questão aberta → resolvida)

O container `rfexp` builda de `RF NEXt` (OneDrive): `alpine:latest` + python3 + Pillow + **tesseract-ocr**, copiando exatamente 5 arquivos: `index.html` (SPA de 207KB), `server.py`, logo, `rfnext-game-data.sqlite` (base do jogo, read-only, embutida) e `market-template.csv`. Estado mutável em `/data` (volume): `rfnext.db` (usuários, snapshots de mercado), `market.csv` e imagens vindos da ferramenta de captura Windows.

**`craft.html` em `rfexp.karvalho.dev.br/craft.html` é inalcançável por DUAS quebras independentes:**
- não entra na imagem (não está no COPY nem existe na raiz de `RF NEXt`; o compose não monta `Site\projects\rf-next`);
- mesmo se entrasse, o roteador do `server.py` tem whitelist de 2 arquivos estáticos (`karvalho-logo.png`, `market-template.csv`) e manda **todo o resto para `index.html`**.

A expectativa registrada na memória do MCP (craft.html publicado no rfexp) **não é cumprível na arquitetura atual**. E provavelmente nem precisa ser: o SPA já tem craft **nativo** via `/api/craft/*` lendo o SQLite do jogo. O `calc/craft.html` canônico é outra linhagem — calculadora offline self-contained de duplo-clique. **Decisão sua:** (a) descontinuar a ideia do craft.html no rfexp e corrigir a memória (recomendado), ou (b) adicionar o arquivo ao COPY + à whitelist e rebuildar.

**Governança dividida:** o handoff declara `K:\MCP\projects\rf-next` como projeto oficial, mas o app servidor (o que o compose builda) vive no OneDrive `RF NEXt`, fora de VCS e num contexto de build frágil (OneDrive pode hidratar arquivos sob demanda durante `docker build` — o SQLite grande é o mais exposto). Recomendação: mover o contexto de build para o repo canônico.

## 3) O app RF Next real (não documentado em lugar nenhum)

O `server.py` de 1054 linhas é um "quarto pilar" que nenhum dos dois docs descreve: app multiusuário com estado por usuário (`/api/state`, limites e sanitização), histórico compartilhado opt-in (`/api/history/general`, flag `share`), mercado com snapshots e série histórica, craft e game-data (itens/NPCs/skills/mapas de `rfnext-game-data.sqlite`, aberto `mode=ro`), OCR (`/api/ocr`, MCP→tesseract), imagens de mercado com proteção contra path traversal, SQL 100% parametrizado, guardas de decompression bomb. Qualidade acima do que os docs sugerem. Riscos: sem rate limit no app (OCR de 12MB + tesseract concorrente pode exaurir CPU — mitigar no gateway), `alpine:latest` sem pin, atualização da base do jogo exige rebuild.

## 4) Stack MCP (K:\MCP) — arquitetura real vs. doc consolidado

O Compose sobe só **3 serviços**: `mcp-db` (Postgres 16, 127.0.0.1:5432), `mcp-control` (control-api FastAPI, 127.0.0.1:8080, fala com Docker só via `socket-proxy` com escopo mínimo) e `mcp-socket-proxy`. **`local-ai-mcp` (porta 8000), Ollama e host-worker são NATIVOS no Windows** — o próprio cabeçalho do compose documenta isso. O doc consolidado ("orquestração por Docker Compose; local-ai como serviço principal") descreve uma arquitetura que não existe.

O desenho real é bom: control-api valida tools contra JSON Schema, allowlist fechada de host_commands (comandos shell fixos, nunca texto do banco), prompts por stdin, sanitização por regex, heartbeat por token de worker. Confirmações importantes de segurança. Mas há riscos reais:

- **Alto — o serviço público é o não-autenticado.** O túnel do Site publica `mcp.karvalho.dev.br` → `local-ai-mcp:8000`, que **não tem autenticação de aplicação** (OAuth listado como "futuro" no README). O serviço COM token (control-api :8080) é local-only. A proteção pública depende 100% do Cloudflare (e o firewall da porta 8000 na LAN é config manual). Prioridade: colocar auth no local-ai ou Cloudflare Access na rota.
- **Médio — `container_action` sem allowlist de nome**: quem tem o CONTROL_TOKEN pode start/stop/restart **qualquer** container do host (dentro do que o socket-proxy permite).
- **Médio — segredos sem ignore**: só `stack/` tem `.gitignore`; `host-worker/.env` (com senha de banco) e `local-ai-mcp/.env` não têm. E não há `.git` em nenhuma dessas pastas de infra — mesma situação do Site: **infra crítica sem versionamento**.
- Menores: porta 5432 publicada apesar de TODO de remoção; rate-limit vira balde único "anon" com auth Bearer; comparação de token sem `compare_digest`; debug de cmdline nos logs do worker.
- **Acoplamento invisível**: a exposição pública do MCP mora no repo do Site. Mexeu no cloudflared do Site → MCP público cai sem sinal em K:\MCP.

## 5) Projetos satélites — vs. doc consolidado

- **Poke Idle**: supervisor Playwright multi-conta (Node 20/TS, Chromium headless) com dashboard em 127.0.0.1:8787, hardening bom no compose (`read_only`, `cap_drop: ALL`). O doc erra o bootstrap ("via .env" — o README nega explicitamente; config é YAML) e omite os 3 modos de deploy (Docker, systemd, Tarefa Agendada Windows) e os gates `rulesAcknowledged`/`SAFE_STOP`. Estado: **nunca validado em produção** (o próprio README admite que build/testes não rodaram).
- **Controlar tela**: nome real do produto é **"Ronaldinho — Proteção por Barra de Vida" v1.3.0**, distribuído por **GitHub Releases** (`Carvalho3009/ronaldinho-protecao`) — o doc cita v1.1.0 via OneDrive, ambos desatualizados. Risco: auto-update baixa binário do GitHub **sem verificação de assinatura** (cadeia de suprimento) e o exe roda como admin.
- **RF Kojiro**: projeto genuinamente distinto do rf-next (RF Online servidor privado, editor Electron de planilhas → futura RF Data Studio). Spec aprovada com ajustes; bloqueadores conhecidos: path traversal no restore de backup, app só roda em modo dev. Pasta canônica é `RF Kojiro` (com espaço); a `rf-kojiro` do cadastro está vazia — inconsistência a arrumar.
- **painel-v2**: só design (levantamento fable × gpt-5.6-sol, 10 decisões D1-D10 aguardando você). Nenhum código.
- **aion2-global**: editorial puro, fase 1 sem site/automação. OK.
- **game-data-monitor**: registrado no stack, **sem pasta** em `K:\MCP\projects` — cadastro órfão ou pasta em outro lugar.
- **ROOC Americas**: a alegação do doc sobre "workflow youtube metadata" não é confirmável pelos arquivos auditados (só pelo histórico de memórias); manter no doc só com fonte citada.

## 6) Plano de takeover — versão final priorizada

**P0 — esta semana (estanca risco)**
1. Versionamento: `git init/commit/remote` para **Site** e **K:\MCP** (stack, control, host-worker, local-ai-mcp — com `.gitignore` cobrindo todos os `.env`) — hoje nada disso tem histórico.
2. Autenticação no MCP público: Cloudflare Access na rota `mcp.karvalho.dev.br` ou token no local-ai-mcp.
3. Decisão craft.html (descontinuar × implementar COPY+whitelist) e corrigir a memória do MCP correspondente.
4. Amanhã (23/07) é a abertura prevista do ROOC Americas — o pipeline editorial (build 6h) consome `..\ROOC AM\conteudo` do OneDrive; congelar mudanças estruturais até passar a abertura.

**P1 — próximas 2 semanas**
5. Mover contexto de build do rfexp para dentro do repo canônico rf-next (sai do OneDrive); pin de `alpine`/`cloudflared`; preencher `RFNEXT_VISION_TOKEN` (.env + .env.example) para ativar o OCR via MCP.
6. Remover `Site\projects\rf-next` (stale) e o mecanismo morto `users.caddy`/`manage-user.ps1`; adicionar backup de `rfnext-data` ao checklist.
7. Allowlist de nomes em `container_action`; remover publicação da 5432; `compare_digest`; corrigir balde do rate-limit.
8. Unificar a fonte editorial ROOC (decidir: OneDrive continua mestre do conteúdo ou migra para `K:\MCP\projects\rooc-americas`) — hoje o site publica de uma pasta e o "canônico" é outra.

**P2 — quando houver folga**
9. Reescrever os dois documentos técnicos com base nestes 3 relatórios (o consolidado precisa de correção em TODAS as seções exceto ROOC AM e Poke Idle parciais).
10. Endurecer senha do Authentik (zxcvbn/HIBP), CSP na rota auth, healthchecks, resolver `rf-kojiro` vs `RF Kojiro`, cadastro do game-data-monitor, release pipeline assinado do Ronaldinho.

---
*Auditoria executada por 3 agentes paralelos (infra MCP: Opus; RF Next: Opus; satélites: Sonnet), com planejamento e revisão final Fable — fluxo padrão do projeto. Relatórios anteriores: `RELATORIO_AUDITORIA_KARVALHO.md`, `AUDITORIA_DOC_CONSOLIDADO.md`.*
