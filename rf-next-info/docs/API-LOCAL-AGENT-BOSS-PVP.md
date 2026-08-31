# API local do RF QOL Agent para Boss e PvP

## Finalidade

Esta API permite que um programa autorizado, executado no mesmo Windows, receba
eventos já decodificados e sanitizados para construir monitores e overlays de
Boss e PvP. O consumidor não captura tráfego, não executa decoder e não controla
o jogo.

A API pertence exclusivamente ao executável RF QOL Agent. Ela não depende do
Desktop e continua disponível quando o servidor central ou a outbox estiverem
indisponíveis.

## Segurança e pareamento

- endereço fixo: `http://127.0.0.1:17621`;
- autenticação: `Authorization: Bearer <token>` em todas as rotas;
- o token aleatório é protegido por DPAPI para o usuário Windows atual;
- o token só deve ser exibido por uma ação explícita de pareamento no Agent;
- API somente leitura, sem CORS, comandos ou bind na rede local;
- não expõe pacote bruto, endereço/fluxo de rede, UID de sessão/login/autenticação,
  credencial, `installation_id`, chave privada ou opcode `0x0101`;
- o UID permanente do personagem é um campo aprovado e pode acompanhar nome,
  level e guilda para sincronização do diretório público e correlação dos monitores.

## Descoberta e saúde

### `GET /api/agent/v1/capabilities`

Informa versão do contrato, domínios, tipos de evento e limites. O consumidor
deve verificar esta rota ao conectar e ignorar tipos desconhecidos para manter
compatibilidade futura.

### `GET /api/agent/v1/health`

Informa estado sanitizado da captura, sessão, feed local e outbox. O token e os
identificadores da instalação nunca fazem parte da resposta.

## Encontros consolidados para o Monitor de Boss e Discord

### `GET /api/agent/v1/boss/encounters`

Retorna o estado atual dos encontros que o Agent já confirmou. Esta é a rota
preferencial para o Monitor de Boss e seu painel de Discord: não exige que o
consumidor reconstrua o combate a partir do ring buffer e não pisca quando não
há um novo pacote entre duas consultas.

Cada encontro contém:

- `boss`: nome, índice, level, HP atual, HP máximo e percentual;
- `players`: nome, UID permanente do personagem, `guild_id`, `guild_name` e
  dano total acumulado naquele Boss; o campo legado `guild` continua como alias
  de `guild_name` para consumidores anteriores;
- `damage_total`, `started_at` e `updated_at`;
- `client_ref` e `encounter_ref` opacos para separar clientes e encontros.

O dano é acumulado por encontro, não calculado apenas sobre os últimos
segundos. Eventos repetidos com o mesmo `event_id` são ignorados antes da soma.
O estado de um Boss é removido somente por desaparecimento, morte, resultado
confirmado ou encerramento da sessão correspondente; ausência momentânea de
novos eventos não apaga o painel.

Exemplo:

```http
GET /api/agent/v1/boss/encounters
Authorization: Bearer <token>
```

O contrato atual é `rf-qol.local-boss-encounters/v1` e aparece em
`capabilities.snapshots.boss_encounters`. Agentes anteriores continuam
compatíveis pelo feed genérico descrito abaixo.

## Leitura dos eventos

### `GET /api/agent/v1/monitor/events`

Parâmetros:

- `after`: último cursor processado, ou `0` na primeira leitura;
- `domains`: `boss`, `pvp` ou `boss,pvp`;
- `limit`: de 1 a 250 eventos;
- `wait_ms`: espera por novos eventos, de 0 a 1000 milissegundos.

Exemplo:

```http
GET /api/agent/v1/monitor/events?after=120&domains=boss,pvp&limit=100&wait_ms=1000
Authorization: Bearer <token>
```

O consumidor salva `next_cursor` e o usa como `after` na próxima requisição. Se
`reset_required` for verdadeiro, o cursor ficou atrás do ring buffer; o programa
deve limpar apenas seu estado vivo e reconstruí-lo com os eventos retornados.
Não deve apagar históricos já concluídos.

Cada evento contém referências opacas de sessão, stream, cliente e entidades.
Essas referências servem para correlação dentro do contrato. A única identidade
canônica do jogo liberada é `character_uid`; UIDs transitórios de entidades
continuam convertidos em referências de sessão.

Eventos compartilhados de combate podem pertencer a Boss ou PvP. A API não
transforma automaticamente um jogador próximo em inimigo e não classifica dano
ambíguo como PvP. O consumidor deve correlacionar aparições, referências e
relações confirmadas antes de exibir uma classificação.

O domínio `boss` também inclui `world.players_appeared` e
`world.guilds_observed`. Assim, consumidores do feed genérico conseguem
relacionar cada `character_uid` ao `guild_id` e ao respectivo `guild_name`, sem
misturar personagens de clientes ou sessões diferentes.

## Limites operacionais

- Boss possui prioridade máxima no processamento interno do Agent. A regra
  abrange eventos explícitos, combate classificado como Boss e aparição ou
  desaparecimento necessário para manter HP e DPS consistentes;
- essa prioridade é exclusivamente local e não envia eventos de Boss ao site;
- ring buffer padrão: até 10.000 eventos e 16 MiB, valendo o primeiro limite;
- resposta: até 256 KiB;
- concorrência: até 4 requisições;
- taxa: até 20 requisições por segundo;
- long poll: até 1 segundo;
- falha ou lentidão do consumidor nunca bloqueia captura, decode ou envio ao
  servidor central.

## Ciclo recomendado do consumidor

1. Receber do usuário o endereço e o token exibidos pelo Agent.
2. Consultar `capabilities` e validar os domínios necessários.
3. Consultar `health` e aguardar `session_active=true` quando aplicável.

O `health` também publica apenas contadores numéricos sanitizados de captura e
decoder (`received_packets`, `processed_packets`, `decoded_events`, descartes e
reinícios de rota). Ele não expõe bytes de pacote, portas individuais, IPs,
fluxos ou identificadores internos. Esses contadores permitem distinguir falha
de captura, decode e projeção sem abrir arquivos brutos.
4. Ler eventos por long poll, sempre persistindo o último `next_cursor`.
5. Isolar estado por `session_ref` e `client_ref`; nunca misturar clientes.
6. Ao receber `session.lifecycle`, iniciar, pausar ou encerrar somente o estado
   da sessão correspondente.
7. Ao desconectar, tentar novamente com espera progressiva, sem gerar carga alta.

## Build portátil do Agent

O pacote separado pode ser validado localmente com:

```powershell
.\packaging\build-agent.ps1
```

O resultado é `dist\RF QOL Agent\RF QOL Agent.exe`. Esse processo não gera
instalador, não configura servidor e não publica o artefato.
