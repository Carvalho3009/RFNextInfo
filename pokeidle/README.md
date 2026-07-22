# Poke Idle Supervisor

Supervisor multi-instância para manter o cliente oficial do Poke Idle World em Chromium Playwright headless, com perfil persistente e isolado. A solução **sempre mantém um processo Chromium por instância ativa**; não afirma operar sem navegador.

O projeto é seguro por padrão: os exemplos vêm desabilitados, as regras públicas sobre automação ainda não foram confirmadas e nenhum seletor autenticado foi inventado. Enquanto esses dois gates estiverem incompletos, a instância termina em `SAFE_STOP` sem abrir o jogo.

## O que está implementado

- Node.js 20+, TypeScript strict e Playwright Chromium headless.
- Um worker Node e um Chromium por conta; um contexto persistente e uma página.
- Perfis exclusivos em `data/profile/<id>`; nunca usa Chrome pessoal.
- Lock global e por perfil, heartbeat, watchdog, backoff exponencial com jitter, orçamento de reinícios e circuit breaker.
- Máquina de estados completa do `BOOT` ao `SAFE_STOP`.
- Dashboard responsivo para várias instâncias, com start/stop/restart, HP, helpers, hunt, métricas e histórico compacto.
- Health check local em `GET /healthz` e stream de status em `/api/events`.
- Logs NDJSON rotativos, redação de segredos e screenshot somente em erro fora da tela de login.
- Métricas de CPU/heap/DOM; RSS da árvore Chromium no Linux.
- Docker, systemd e Tarefa Agendada do Windows.
- Testes unitários, de soak simulado e E2E do dashboard.

Compras não estão implementadas nesta versão. Falta de poção/revive causa `SAFE_STOP`: não há gasto de gold implícito e gasto de diamantes não é representável. Captura permanece ação manual do operador no cliente oficial.

## Pré-requisitos

- Node.js 20 ou superior.
- Aproximadamente 1 GiB livre para o Chromium e dependências na primeira instalação.
- Uma confirmação oficial, arquivada pelo operador, de que a automação proposta é permitida.
- Uma conta de teste/sessão autorizada para descobrir o DOM autenticado.

## Instalação local

PowerShell:

```powershell
Copy-Item config.example.yaml config.yaml
Copy-Item .env.example .env
npm ci
npm run bootstrap
npm run build
```

O aplicativo não carrega `.env` automaticamente para evitar uma dependência e ambiguidades. Defina o token no ambiente antes de iniciar:

```powershell
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$env:POKEIDLE_DASHBOARD_TOKEN = [Convert]::ToHexString($bytes)
$env:POKEIDLE_CONFIG = "config.yaml"
```

Linux:

```bash
cp config.example.yaml config.yaml
npm ci
npm run bootstrap
npm run build
export POKEIDLE_DASHBOARD_TOKEN="$(openssl rand -hex 32)"
export POKEIDLE_CONFIG=config.yaml
```

Nunca coloque senha do jogo em `.env`, YAML, código ou linha de comando.

## Gates antes de produção

1. Confirme as regras com a equipe oficial e arquive a evidência. Só então altere `game.rulesAcknowledged` para `true`.
2. Faça Recon autenticado e preencha o contrato conforme [discovery/ui-contract.template.md](discovery/ui-contract.template.md). Cada locator precisa ser único e ter pós-condição verificada.
3. Confirme que Auto-Potion e Auto-Revive são helpers nativos já disponíveis e não abrem compra/VIP.
4. Provisione a sessão no perfil isolado. Depois do build:

```powershell
npm run provision -- principal
```

Esse comando abre **temporariamente** uma janela Playwright isolada apenas para login manual. A execução persistente continua headless. O programa não lê nem registra a senha. Não tente provisionar duas instâncias da mesma conta ao mesmo tempo.

5. Rode os testes simulados e, com autorização, um teste live conservador e o soak de 24 h.

## Comandos operacionais

Com o token e a configuração definidos no ambiente:

```powershell
npm start          # foreground; use systemd, Docker ou Task Scheduler em produção
npm stop           # solicita SAFE_STOP a todas as instâncias
npm restart        # reinicia os workers pelo supervisor
npm status         # imprime estado e métricas
npm logs           # últimas 50 linhas por log, já redigidas
npm test           # build + testes unitários/simulados
npm run test:e2e   # dashboard em Chromium headless
npm run test:soak  # 250 mil ciclos determinísticos; não substitui soak real
```

Dashboard: `http://127.0.0.1:8787`. O token fica apenas em `sessionStorage` e é exigido para comandos mutáveis. Para acesso remoto, use VPN ou reverse proxy HTTPS; não exponha a porta diretamente.

## Múltiplas instâncias

Adicione entradas em `instances` com IDs únicos. Cada ID deriva automaticamente:

```text
data/profile/<id>
data/locks/<id>.lock
data/logs/<id>.ndjson
data/errors/<id>/
```

Uma conta/perfil não deve ser repetida. Cada instância custa um processo Chromium próprio; dimensione pelo p95 medido mais 30% de folga.

## Otimização segura

O baseline permite imagens, fontes e CSS. Somente `--mute-audio` é aplicado por padrão. `blockMedia` e `blockedUrlPatterns` permanecem desativados até teste A/B autenticado. A denylist só bloqueia URL sanitizada exata de imagem, fonte ou stylesheet; scripts, documentos, XHR, `fetch`, WebSocket e recursos desconhecidos sempre passam.

Não habilite flags agressivas como `--disable-gpu`: elas podem aumentar CPU. Não bloqueie `.dat`, `.spr`, service worker ou recursos por extensão. Veja [reports/resources.md](reports/resources.md).

## Docker

```bash
cp config.docker.example.yaml config.docker.yaml
export POKEIDLE_DASHBOARD_TOKEN="$(openssl rand -hex 32)"
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f supervisor
docker compose restart supervisor
docker compose stop supervisor
```

O compose usa `restart: unless-stopped`, `init`, usuário não-root, filesystem somente leitura, volume persistente, `no-new-privileges` e capabilities removidas. O dashboard é publicado somente em `127.0.0.1`.

## systemd

1. Instale o projeto compilado em `/opt/pokeidle` e os dados em `/var/lib/pokeidle`.
2. Coloque config em `/etc/pokeidle/config.yaml` com `runtime.dataDir: /var/lib/pokeidle`.
3. Crie `/etc/pokeidle/pokeidle.env` com permissão `0600` e apenas `POKEIDLE_DASHBOARD_TOKEN=...`.
4. Instale `deploy/systemd/pokeidle.service`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pokeidle
sudo systemctl status pokeidle
sudo journalctl -u pokeidle -f
sudo systemctl restart pokeidle
sudo systemctl stop pokeidle
```

## Windows sem janela persistente

Compile e defina `POKEIDLE_DASHBOARD_TOKEN` como variável de usuário/máquina; depois, em PowerShell:

```powershell
.\deploy\windows\install-task.ps1
Start-ScheduledTask -TaskName PokeIdleSupervisor
Get-ScheduledTaskInfo -TaskName PokeIdleSupervisor
Stop-ScheduledTask -TaskName PokeIdleSupervisor
.\deploy\windows\uninstall-task.ps1
```

A tarefa usa logon `S4U` e não abre janela. O worker também usa `windowsHide: true`.

## Segurança e dados

- Cookies e sessão ficam apenas no perfil Chromium, que deve ter ACL restrita e disco criptografado.
- Logs recusam password, authorization, cookies, tokens, secrets, storage state, query e hash de URLs.
- Não se registra console integral do navegador, DOM integral, corpos de rede ou frames WebSocket.
- Popups inesperados são fechados; não viram segunda página.
- DOM ausente/duplicado, login expirado, falta de suprimentos, modal de gasto ou ação proibida terminam em parada segura.

## Estado de validação

O sandbox desta entrega bloqueou o registry do npm, então não foi possível executar `npm ci`, build ou testes aqui. Também não houve sessão autenticada nem soak live. Isso é um bloqueador de aprovação, não uma alegação de sucesso. Consulte [reports/tests.md](reports/tests.md), [reports/discovery.md](reports/discovery.md) e os relatórios dos juízes.
