# RF QOL 2.0 — Banco PvE, status e subsessão automática

Status: programa e contrato do site implementados em código-fonte em 2026-08-16. Sem deploy.

## Banco PvE

- A chave canônica do monstro continua sendo `npc_index + protocol_version`.
- Uma observação idêntica atualiza somente `last_seen_at` e não devolve o
  registro à fila de envio.
- Locais confirmados são preservados em tabela aditiva, com mapa e coordenadas quando disponíveis.
- Coordenadas usam bucket espacial versionado de 1 unidade para absorver pequenas variações.
- O primeiro HP máximo válido permanece canônico.
- Um HP divergente entra em uma fila local de revisão e não substitui nem reenvia o valor canônico automaticamente.
- O payload antigo permanece compatível para o Banco PvP. O Banco PvE usa rota
  e confirmação próprias, sem voltar a misturar mobs no lote PvP.

### Licenciamento 2.0

- Monitor PvE, Banco PvE, HP/localizações, fila de divergência, sincronização e
  contexto de mobs exigem lease v3 ativa e `monitor-pve`;
- `base` mantém o motor de status, regras, alertas e sons, mas não produz nem
  expõe sinais derivados de PvE quando `monitor-pve` não estiver liberada;
- localização originada no Módulo Mapa exige também `map`; sem `map`, uma
  observação PvE válida pode permanecer sem localização, sem reutilizar o último
  mapa conhecido;
- o gate vale para interface, workers, operação direta e envio/consulta do site.

### Delta e confirmação do site

- rota dedicada: `POST /api/import/pve-observations`;
- autenticação atual: token do Profile, lease v2 e `Idempotency-Key` SHA-256;
- na 2.0, após a migração aprovada, a rota passa a validar lease v3 ativa com
  `monitor-pve`; o contrato v2 permanece compatível para clientes 1.x;
- schema de entrada: `rf-qol.pve-observations.delta`, versão 1;
- lote limitado a 500 registros e composto por `mob`, `location` e
  `hp_candidate`;
- cada registro possui `observation_id` determinístico sobre o conteúdo
  material; horários de primeira/última observação não alteram a identidade;
- schema de resposta: `rf-qol.pve-observations.ack`, versão 1;
- o site confirma cada `observation_id` como `accepted`, `known` ou `conflict`;
- o programa libera somente os IDs explicitamente confirmados. Ausentes ou
  respostas incompatíveis permanecem pendentes para retry;
- lotes repetidos devolvem o ack armazenado e não reaplicam mudanças;
- localização é aditiva e deduplicada por `location_key`;
- HP divergente nunca substitui o canônico: entra em
  `observed_mob_hp_candidates` para revisão e recebe ack `conflict`.

O contrato aceita apenas campos decodificados e sanitizados. Payload bruto,
UID de jogador, token, ticket, credencial e opcode `0x0101` não fazem parte do
delta, do ack ou das tabelas PvE.

## Status

O snapshot possui dimensões concorrentes:

- disponibilidade: `available`, `offline` ou `unknown`;
- atividade: `idle`, `farm`, `pvp`, `boss` ou `unknown`;
- sinais: `threat`, `under_attack`, `low_hp`, `boss_nearby` e `teleporting`.

O badge único usa `Teleportando > PvP > Farm > Ocioso`. Farm depende de dano
positivo causado pelo personagem local a um mob ou abate de mob atribuído a ele
nos últimos 30 segundos; EXP isolada e seleção de alvo não ativam Farm. PvP exige
dano positivo causado ou recebido. Boss permanece como sinal concorrente de
proximidade, sem substituir o badge. Os sinais auxiliares continuam independentes
na API.

## Saúde da API local

- `GET /api/v1/health` informa versão, RAM atual, orçamento escolhido e pressão.
- O estado da captura distingue `idle`, `active`, `paused` e `pending`.
- O último checkpoint informa somente disponibilidade, motivo e idade.
- O stream expõe apenas contadores de fila, retenção, processamento, descarte e
  atraso; sessão, UID, fluxo, porta, caminho e payload não entram no contrato.
- A API aceita no máximo quatro requisições simultâneas e 20 requisições por
  segundo, mantendo respostas em até 256 KiB.

## Regras e alertas locais

- O mesmo snapshot de status alimenta regras prontas para ameaça confirmada,
  entrada em Farm e início de Teleporte.
- Cada regra usa somente sinais cujas features de origem estejam liberadas;
  `base` não substitui `monitor-pve`, `monitor-pvp`, `monitor-boss` ou `map`.
- Farm e Teleporte disparam apenas na transição; Ameaça pode repetir enquanto
  persistir, respeitando o intervalo mínimo configurado pelo usuário.
- O intervalo mínimo aceita de 5 a 300 segundos e vale também para os demais
  alertas visuais/sonoros.
- Condições arbitrárias, scripts, URLs e conteúdo executável não são aceitos.

## Banco PvP e curadoria

- Neutro sem guilda visto em uma única sessão fica em `quarantine`.
- Confirmação manual, guilda/status observado ou uma segunda sessão promove o
  UID a `final`.
- Somente `final` entra no payload pendente para o site.
- A interface mostra Banco Final, Quarentena, sessões e aparições; não existe
  exclusão automática.
- Um índice aditivo cobre curadoria, status e ordenação por nome sem alterar os
  registros existentes.

## Checkpoints de sessão

- A leitura grava um checkpoint depois da ingestão; pausar/finalizar promove o
  motivo do último ponto correspondente.
- A chave `session_id + last_event_id` impede crescimento quando nenhuma
  informação nova foi persistida.
- Checkpoints guardam apenas contadores, último evento e tamanho persistido; não
  duplicam payloads nem ampliam as coleções quentes em RAM.

## Visão geral — Mobs próximos

- Reutiliza `nearby_monsters` do monitor do cliente selecionado, sem iniciar
  outro decoder ou guardar outra coleção de eventos.
- Descarta registros mortos ou vencidos e agrupa aparições repetidas pelo nome
  apresentado, mantendo uma única linha por tipo de mob.
- Mostra somente nome, nível e HP máximo positivo; não consulta nem apresenta
  alvo atual, HP atual, percentual ou DPS.
- Quando o mesmo nome tiver mais de um nível ou HP máximo confirmado na janela,
  apresenta os limites observados em vez de duplicar a linha.
- A tabela possui rolagem própria para não ampliar indefinidamente o cartão nem
  a memória da interface.

## Subsessão automática

- A opção é explícita por subsessão e pode iniciar sem mapa, spot ou mobs.
- A tela **Nova subsessão** oferece também **Buscar localização e mobs agora**;
  essa ação apenas preenche o rascunho usando o contexto recente do cliente
  selecionado e não cria nem inicia a subsessão.
- O contexto usa somente o monitor e o Módulo Mapa do mesmo `client_key`.
- Mobs próximos confirmados são acumulados sem duplicação.
- O spot só é preenchido quando todos os mobs observados produzem uma única correspondência no catálogo.
- Quando o mapa ou os mobs forem encontrados, mas o spot continuar ambíguo, a
  tela mantém o spot vazio e explica o motivo ao usuário.
- Um mapa/spot já preenchido nunca é substituído pela inferência.
- A edição manual desativa a ambiguidade ao prevalecer sobre dados automáticos.

## Pendências com gate externo

- política de aprovação ou rejeição de HP divergente;
- validação simultânea com dois clientes reais;
- política de idade, compactação e remoção do Banco PvP e das sessões.

## Validação

Os testes automáticos cobrem ack parcial, retry somente do restante, ausência
de reenvio de mob conhecido, localização nova, conflito de HP e idempotência do
site. Nenhum teste manual ou deploy faz parte desta etapa.
