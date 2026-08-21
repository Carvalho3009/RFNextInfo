# Plano inicial — RF QOL 2.0

Data: 16 ago 2026
Atualizado: 17 ago 2026
Estado: base local da 2.0 em implementação e validação
Escopo desta etapa: programa local e portátil de staging, sem instalador, publicação, release ou deploy

## 0. Progresso local

| Frente | Estado em 16 ago 2026 | Limite atual |
|---|---|---|
| Ranking de EXP | Snapshot Top 100, integridade parcial/completa, histórico local com data/hora, nível, progresso, ganho entre capturas e ganho/hora, além de envio automático do snapshot completo pelo contrato existente. Resultados idênticos dentro de uma janela de uma hora não criam novas entradas. | Nenhuma migração ou implantação do site foi realizada. |
| Módulo Mapa | Estado por rota, índice confirmado por resposta de teleporte, coordenadas, proximidade, remoção, limite de dois clientes, aba local e catálogo 1.28.5 com nomes PT/EN implementados. Há 49 plantas da base 1.29.7 para Novus, Albern, Android, Nemesis, mineração e mapas orbitais; Novus possui 56 regiões oficiais e centro exposto na interface/API. Andares são regiões fixas do mapa-base, inclusive no preenchimento de subsessões. Na Visão geral, a planta é compacta, fixa e não recentraliza o personagem; zoom, arraste e foco ficam restritos à aba Mapa. | A validação simultânea real de dois clientes será feita após gerar o executável candidato. Plantas compartilhadas por andares preservam a origem no manifesto. |
| API local | `health`, `map` e `status` em `127.0.0.1`, Bearer protegido por DPAPI, desligada por padrão; `health` expõe somente RAM/orçamento, captura, checkpoint e métricas permitidas do stream. | Sem API remota e sem CORS. |
| Sessões na rede | Primeira entrega especificada como consulta pull e somente leitura. A coleção visual começa com um cliente; **Adicionar cliente** pergunta a origem e já adiciona PC/emulador em vaga compatível. Clientes adicionados podem ser excluídos da interface sem apagar dados. | Pareamento, TLS, IDs opacos, concorrência, cliente externo e API LAN continuam em planejamento; **Externo via API** é informado como indisponível e não cria entrada fictícia. |
| Licença 2.0 | Cliente, emissor v3 e consumidor dual do site implementados de forma aditiva, sem cotas de quantidade, com sete features, até 7 dias e tentativa única por abertura. Perfil portátil `2.0.0-rc1 (Homologação)` isolado, licença temporária de staging ativa e site remoto desativado. | Staging integrado do site, chave definitiva, produção e publicação permanecem pendentes. |
| Banco PvE | Observações idênticas não reenviam, múltiplos locais usam bucket de 1 unidade, HP divergente entra em revisão, aba local e delta/ack por registro com o site implementados. | Código do site não implantado; política humana de aprovação/rejeição de HP continua pendente. |
| Subsessão | Preenchimento contínuo opcional por proximidade e botão no rascunho para buscar imediatamente mapa, spot e mobs do cliente selecionado; campos MAU, launcher e poção de EXP foram adicionados com estado de evidência explícito. | Detecção automática desses três usos depende das séries marcadas descritas em `PROTOCOLO-EVIDENCIAS-SUBSESSAO.md`; spot só é inferido quando o catálogo produz uma única correspondência. |
| Monitores | A aba PvE mantém somente o alvo atual; a Visão geral exibe mobs próximos sem repetição, com nível e HP máximo, sem usar alvo ou HP atual. A lista PvP troca atomicamente a cada 10 s sem limpar o stream. | A validação em captura real será feita após gerar o executável candidato. |
| Status | Dimensões concorrentes e badge `Teleportando > PvP > Farm > Ocioso` implementados; Farm usa dano/abate de mob em 30 s e a API preserva `null` sem evidência. | Critérios adicionais continuam dependentes de evidência e decisão do owner. |
| Alertas | Som WAV local, drops confirmados, múltiplas categorias de raridade selecionáveis, intervalo mínimo configurável e regras para Ameaça, entrada em Farm e Teleporte implementados. A origem oficial dos drops é o evento de recompensa enviado pelo servidor (`drop_item_field`), nunca o texto do chat. | O histórico aceita somente resultados confirmados com item e quantidade válidos. |
| Banco PvP | A base existente, Banco Final, Quarentena, decisões manuais e compatibilidade atual são preservados sem novas alterações funcionais na 2.0. | Evolução, retenção e limpeza foram adiadas pelo owner para a 2.1. |
| Memória e sessões | Orçamento de 256 MiB a 2 GiB, filas/caches limitados, compactação ativa sob pressão e checkpoints idempotentes após leitura, pausa e finalização implementados; o último salvamento aparece na Visão geral. | As amostras reais 8 h/11 h/14 h ainda falham estabilidade; o orçamento não é reserva rígida do Windows e o gate prolongado continua pendente. |
| Leilão | A projeção sanitizada agora mostra vendas próprias, compras confirmadas e histórico com tipo bruto ainda não validado, preservando ID opaco e isolamento por personagem. | Banco do site, API, coordenação da guilda e anti-undercut continuam na 2.1. |
| Interface | Shell e Visão geral portados para o mockup 2.0. O Resumo Geral usa cartões compactos com identidade/equipamento no cabeçalho e métricas da sessão no corpo. Todas as tabelas permitem ajustar tamanho e ordem das colunas, com autofit por duplo clique. **Monitoramento**, **Bancos**, **Sessões** e **Configurações** permanecem consolidados. | Comparação visual Qt automática concluída; aprovação visual manual do owner permanece pendente. |

Validação automática atual: 393 testes passaram em 97,3 s, sem falhas; nenhum
teste manual foi executado. A rodada inclui checkpoints,
curadoria/quarentena PvP, regras de alerta, isolamento de drops por cliente,
retenção das respostas de teleporte no stream, catálogo de 49 plantas, 56
regiões do Novus, navegação da planta inteira e limites de memória. O ensaio
isolado anterior de 12 ciclos completos no perfil de 256 MiB liberou todas as
janelas Qt e variou de 85,8 MiB após o primeiro ciclo para 87,5 MiB no último.
O executável candidato também passou pelo autoteste empacotado. Os gates reais
de dois clientes e 10 h, assim como toda validação manual, permanecem pendentes.

## 1. Objetivo

Preparar a evolução do RF QOL para uma linha 2.0 centrada em estado do jogo,
monitores mais simples, bases de conhecimento úteis, integrações de saída e
uso previsível de memória, sem abandonar a captura passiva já validada.

O owner autorizou iniciar e progredir a implementação local. Migração do site,
instalador, publicação, release e deploy continuam fora desta etapa.

## 2. Princípios obrigatórios

- manter a captura passiva por Pktmon e um único decoder sanitizado;
- nunca persistir ou expor tokens, tickets, credenciais, payload bruto ou o
  opcode sensível `0x0101`;
- reutilizar o stream, os monitores, o SQLite e as APIs do site já existentes;
- manter a interface, botões, avisos e mensagens em português; PT/EN continua
  afetando somente os dados do jogo;
- usar `null`/`indisponível` quando identidade, stream ou evidência forem
  insuficientes; ausência de evento não deve ser convertida em fato;
- separar estado vivo, resumo de sessão e histórico persistido;
- na 2.0, licença autoriza módulos por feature e nunca quantidade de clientes;
- tentar revalidar a licença em toda abertura, preservando uso offline somente
  até o `valid_until` assinado de no máximo 7 dias;
- preservar sem regressão as decisões manuais do Banco PvP congelado para a
  2.0; qualquer evolução funcional pertence à 2.1;
- tratar migração de banco, API local, integração com o site, release e deploy
  como gates independentes.
- preservar todas as funcionalidades existentes em cada mudança ou adição;
  exigir teste específico do comportamento novo e regressão automática completa
  antes de marcar uma entrega como concluída.
- evidência real de memória recebida em 2026-08-20: 800 MB em 8 h, 500 MB
  em 11 h e 990 MB em 14 h (tratados conservadoramente como MiB no teste).
  A oscilação não prova vazamento monotônico, mas
  falha o critério de estabilidade por inclinação da cauda e permanece bloqueio
  de release até um ensaio automático prolongado respeitar o limite escolhido.

## 3. Estado atual que deve ser reaproveitado

| Tema | Estado confirmado | Consequência para o 2.0 |
|---|---|---|
| Localização | O decoder atualizado reconhece movimento/posição local (`0x0301`), posição de entidades próximas por `entity_uid` (`0x0302`), respostas de teleporte com `map_index` (`0x0409` em `12010` e `0x0325` em `12020`), warp apenas com posição (`0x040A`) e saída do alcance (`0x030A`). | O módulo, a API local e o catálogo 1.28.5 PT/EN reutilizam essa leitura sem promover o antigo campo bruto de `0x040A`; validação real com dois clientes permanece pendente. |
| Leilão | O decoder já reconhece vendas próprias, liquidações, histórico, cadastro, recadastro e cancelamento. O envio atual de Mercado usa somente listas gerais e ofertas. | Preservar a projeção e a consulta local existentes na 2.0; persistência, API, sincronização da guilda e anti-undercut pertencem à 2.1. |
| Banco PvP | Já existe localmente e no site, com revisão e decisões manuais. | Preservar compatibilidade na 2.0; evolução, retenção e limpeza passam para a 2.1. |
| Monitor PvP | Presença usa aparição confirmada, separada de atualizações de HP; próximos expiram em 15 s. | O flush de 10 s deve ser uma janela de apresentação, não um `clear()` do stream. |
| Monitor PvE | Já produz alvo atual e monstros próximos. | A aba detalhada permanece somente com alvo atual; a Visão geral reutiliza os próximos em uma lista deduplicada de nome, nível e HP máximo. |
| Banco PvE | `mob_observations` no programa e `observed_mobs` no site guardam `npc_index + protocol_version` e HP máximo; localizações e candidatos de HP usam tabelas aditivas. | Delta/ack dedicado, idempotente e por registro está pronto no programa e no código do site, ainda sem deploy. |
| Status/API | Estado concorrente e saídas locais de `health`, `map` e `status` estão implementados, com autenticação e desligados por padrão. | Ampliar contratos somente após definição de consumidores e campos permitidos. |
| Subsessões | Já existem subsessões por cliente, campos de mapa/spot/mobs e rotação automática por tempo. | Preservar o ciclo existente e adicionar preenchimento automático opcional após o início, usando evidência do Módulo Mapa e do monitor PvE. |
| Ranking de EXP do servidor | O layout no TCP `12020` para `0x1A01`–`0x1A04` está confirmado por captura de 14 ago 2026. Parser, ingestão, histórico e aba Top 100 estão implementados. Ao registrar um Top 100 completo e novo, o perfil envia automaticamente ao site com chave idempotente; falhas permanecem elegíveis para nova tentativa. | Snapshots parciais continuam apenas locais. EXP de sessão/subsessão não é fonte desse ranking. |
| Memória | Filas, eventos, fluxos, consultas e caches residentes já obedecem ao orçamento configurável; janelas Qt fechadas são liberadas. Eventos persistidos continuam no SQLite, fora dessas coleções quentes. | Validar os perfis 256/768 MiB por 10 h no executável candidato e depois segmentar sessões persistidas com checkpoint, sem exclusão automática. |
| Licença | A lease v2 atual assina features, cotas `2 PC + 1/5 emuladores`, `next_check_at` e no máximo 24 h offline. | Preservar v2 para 1.x e planejar lease v3 aditiva para a 2.0, sem `connection_limits`/`next_check_at`, com até 7 dias e tentativa em toda abertura. |

## 4. Arquitetura-alvo

Manter um único processo no primeiro ciclo do 2.0. Modularização não significa
microserviços locais.

Fluxo proposto:

1. **Captura passiva** — Pktmon entrega pacotes ao decoder único.
2. **Eventos normalizados** — estruturas sanitizadas e versionadas.
3. **Barramento interno em memória** — fila simples distribui cada evento uma
   única vez aos consumidores autorizados.
4. **Redutores de estado** — o módulo Mapa e os estados de atividade, PvE, PvP,
   Boss, leilão e saúde do stream mantêm apenas o necessário.
5. **Adaptadores** — interface, alarmes, SQLite, API local e sincronização com
   o site consomem snapshots; nenhum cria um segundo decoder.

Camadas de retenção:

- **quente:** estado atual, sinais e janelas curtas em RAM;
- **morna:** checkpoints e resumos da sessão no SQLite;
- **fria:** histórico exportado ou confirmado pelo site, elegível para limpeza
  conforme política aprovada.

## 5. Domínios funcionais

### 5.1 Módulo Mapa e coordenadas

A leitura necessária já está confirmada no decoder atual:

- `move_player_request` (`0x0301`) fornece a posição do personagem local;
- `move_player_update` (`0x0302`) fornece `entity_uid` e posição de jogadores
  ou entidades próximas;
- `request_teleport_result` (`0x0409`, porta `12010`) e `teleport_response`
  (`0x0325`, porta `12020`) fornecem o índice de mapa após sucesso;
- `warp_player` (`0x040A`) fornece posição; a captura de 16 ago 2026 refutou
  que o campo bruto no offset 18 seja `MapIndex`;
- `disappear_unit_list` (`0x030A`) remove entidades que saíram do alcance;
- aparições existentes completam identidade, HP e classificação quando esses
  dados estiverem confirmados.

O 2.0 deve criar um **Módulo Mapa** por cima desses eventos, sem duplicar o
decoder. Cada cliente admitido em uma das duas vagas terá um `MapState`
independente contendo:

- `map_index`, `map_name` e versão do catálogo usado na resolução;
- posição local `x`, `y`, `z`, direção/movimento quando disponíveis;
- `observed_at`, idade, origem e confiança;
- jogadores próximos com `entity_uid`, identidade sanitizada quando conhecida,
  `x`, `y`, `z`, distância relativa, `last_seen_at` e confiança;
- `null` quando algum campo não estiver confirmado.

Capacidade obrigatória:

- o Módulo Mapa mantém no máximo **dois clientes ativos simultaneamente**;
- a ocupação é identificada por `client_key`, sem misturar snapshots quando o
  personagem reconectar ou trocar de rota física;
- um terceiro cliente recebe `map_enabled=false` e
  `reason=capacity_limit`, sem criar `MapState`, reter proximidade ou publicar
  localização;
- atingir o limite do Mapa não interrompe captura, sessão, EXP ou monitores que
  não dependam de localização;
- um terceiro cliente nunca expulsa silenciosamente um dos dois ativos; a vaga
  só muda após liberação confirmada/desconexão com grace period ou seleção
  explícita do usuário;
- interface, saúde e API mostram capacidade `2`, vagas ocupadas e clientes
  limitados, sem tratar o limite como falha geral do programa.

Regras de estado:

- resposta de teleporte bem-sucedida troca o mapa; quando a resposta inclui
  coordenada resolvida, mapa e posição são aplicados no mesmo evento;
- warp atualiza somente a posição do UID correlacionado e nunca usa o campo
  bruto refutado como mapa;
- movimento atualiza somente a entidade e o cliente correspondentes;
- saída confirmada remove imediatamente o jogador próximo;
- TTL continua como proteção quando o evento de saída se perder;
- distância só é calculada quando jogador local e remoto pertencem ao mesmo
  mapa e sistema de coordenadas;
- o nome do mapa é resolvido por catálogo versionado a partir do índice
  decodificado, sem heurística por nome ou posição.

Contrato de saída obrigatório:

- `GET /api/v1/map` devolve o snapshot por cliente no schema
  `rf-qol.map-state/v1`;
- o payload inclui mapa, posição local, jogadores próximos, timestamps,
  staleness, confiança e metadados de capacidade; clientes fora das duas vagas
  recebem somente o estado de limite, nunca a última posição de outro cliente;
- a API é somente leitura; nenhum consumidor externo escreve ou corrige o
  `MapState`;
- o módulo publica snapshots imutáveis; UI, regras e Banco PvE consomem o mesmo
  snapshot;
- um adaptador de envio pode publicar o snapshot para uma API remota aprovada,
  com autenticação, idempotência, retry limitado e destino permitido;
- envio remoto/site vem desligado por padrão e permanece gate separado.

A API nunca inclui fluxo de rede, porta, pacote bruto, token, ticket ou
`0x0101`. Escopo dos jogadores próximos e retenção remota ainda precisam de
aprovação de privacidade. O `entity_uid` pode existir no contrato local para
correlação efêmera, mas o adaptador remoto deve poder omiti-lo ou substituí-lo
por identificador temporário.

### 5.2 Vendas de leilão e coordenação da guilda

Decisão do owner em 16 ago 2026: o Banco de Leilão, a coordenação da guilda,
o anti-undercut e qualquer integração com o site foram adiados para a **2.1**.
Na 2.0, preservar somente a projeção e a aba local já implementadas, sem nova
evolução funcional. O restante desta seção fica como proposta de referência
para a 2.1 e não compõe os gates de aceite da 2.0.

Reaproveitar as mensagens já decodificadas e manter dois tipos de registro:

- **capturado:** fato observado na lista de vendas do próprio personagem;
- **declarado:** intenção manual opcional, caso a guilda queira coordenar antes
  de publicar no jogo.

Campos sanitizados candidatos:

- identificador opaco da listagem, Profile/personagem autorizado, servidor;
- item, refino, quantidade e preço unitário;
- cadastro, expiração, última confirmação e estado
  (`planned`, `active`, `sold`, `cancelled`, `expired`);
- origem e confiança.

Nunca enviar `account_id`, `pc_id`, payload bruto ou identificadores de sessão
do jogo. O site deve usar a identidade autenticada do Profile.

Regra anti-undercut recomendada:

- comparar apenas mesmo servidor, item e refino;
- mostrar menor preço ativo da guilda e quem já possui anúncio;
- avisar quando uma nova intenção/listagem ficar abaixo desse preço;
- não bloquear ações no jogo e não automatizar cadastro/cancelamento;
- reconciliar vendas, cancelamentos e liquidações com os snapshots seguintes.

Visibilidade, prazo de retenção e permissão para editar listagens de outros
membros permanecem decisões do owner. A recomendação inicial é leitura para a
guilda e edição somente pelo dono ou líder.

### 5.3 Banco PvP e volume de bots

Decisão do owner: a base existente permanece compatível na 2.0, mas as regras
propostas nesta seção foram transferidas para a **2.1** e não compõem os gates
funcionais da 2.0.

Separar a base em duas visões sobre os mesmos dados:

- **Banco final:** aliados, inimigos, ignorados e registros editados/revisados;
- **Observações pendentes:** neutros ainda sem evidência suficiente.

Regras propostas:

- nunca classificar bot automaticamente pelo formato do nome;
- não apagar automaticamente registro com guilda/status manual, revisão do
  site ou vínculo usado por uma regra de alerta;
- neutral sem guilda e com uma única aparição entra em quarentena e não polui a
  visualização principal;
- confirmação manual, guilda/status observado ou aparição em duas sessões
  diferentes promove o registro ao Banco Final;
- registros pendentes antigos podem ser compactados ou removidos somente por
  política de retenção aprovada e com contagem/preview antes da limpeza;
- limpeza local e limpeza do site são operações separadas e auditáveis.

A quantidade mínima provisória local é duas sessões. O número de dias e qualquer
regra de compactação/remoção ainda não estão aprovados; por isso não há limpeza
automática.

### 5.4 Monitor PvP com janela de 10 segundos

Interpretação segura recomendada:

- o decoder e o estado interno continuam recebendo eventos sem interrupção;
- a lista de próximos é reconstruída a partir da janela confirmada dos últimos
  10 segundos;
- no tick, um novo snapshot substitui o anterior de forma atômica;
- não chamar `LiveEventStream.clear()`, pois isso apagaria identidade, âncoras e
  evidência usada por outros módulos;
- alvo atual e alerta **Sendo atacado** permanecem imediatos; somente a lista de
  próximos usa o ciclo de 10 segundos.

Se o owner desejar que alvo atual também espere 10 segundos, isso deve ser uma
decisão explícita porque aumenta a latência de uso e dos alarmes.

### 5.5 Monitor e Banco PvE

Monitor PvE:

- manter somente o alvo atual confirmado na aba detalhada do Monitor PvE;
- exibir na Visão geral uma linha por tipo de mob próximo, com nome, nível e HP
  máximo;
- agrupar aparições repetidas e não usar alvo atual, HP atual, percentual ou DPS
  nesse cartão;
- manter o mesmo processamento sanitizado de aparições que alimenta o Banco PvE
  e Boss, sem criar outro decoder ou coleção de combate.

Banco PvE:

- evoluir a tabela existente, não criar outro banco;
- aceitar HP máximo apenas quando positivo e vindo de evento confirmado;
- manter `mob_observations` como ficha canônica de identidade/HP;
- criar estrutura aditiva `mob_locations` no programa e no site para salvar
  múltiplas localizações do mesmo monstro sem sobrescrever a anterior;
- cada localização guarda `npc_index`, `protocol_version`, `map_index`,
  `map_name`, `x`, `y`, `z`, primeira/última observação, confirmações,
  confiança e estado de envio;
- usar uma impressão digital de `npc_index + protocol_version + contexto +
  map_index + célula de coordenada + max_hp`;
- agrupar coordenadas próximas em uma célula/tolerância aprovada para não criar
  uma linha a cada pequeno deslocamento ou reaparição;
- carregar as chaves conhecidas uma vez e ignorar observações idênticas;
- após confirmação do site, não tornar o registro pendente novamente apenas
  porque `last_seen_at` mudou;
- enviar somente mob novo, HP alterado, localização nova/alterada, contexto
  novo ou conflito;
- não sobrescrever silenciosamente HP divergente: registrar candidato, fontes
  e quantidade de confirmações para revisão;
- preservar o campo textual `location` atual somente para compatibilidade; a
  fonte canônica passa a ser mapa e coordenada do Módulo Mapa.

O `contexto` e a tolerância espacial precisam ser fechados. `npc_index +
protocol_version` pode ser insuficiente se HP variar por mapa, dificuldade,
instância ou escala do boss. Quando o mapa ainda estiver indisponível, a
observação fica pendente de localização em vez de ser atribuída ao último mapa
conhecido.

### 5.6 Estado do programa

Os estados não devem ser uma enumeração mutuamente exclusiva. O snapshot deve
ter dimensões concorrentes:

- **disponibilidade:** `available`, `offline` ou `unknown`;
- **atividade:** `idle`, `farm`, `pvp`, `boss` ou `unknown`;
- **sinais:** `threat`, `under_attack`, `low_hp`, `boss_nearby` e outros
  booleanos/`null` versionados.

Regras iniciais:

| Nome na UI | Evidência mínima |
|---|---|
| Ocioso | nenhum Teleporte, dano PvP ou dano/abate PvE está dentro da sua janela |
| Farm | dano positivo causado pelo personagem local a um mob ou abate de mob atribuído a ele nos últimos 30 segundos |
| PvP | dano positivo causado a outro jogador ou recebido pelo personagem local; seleção de alvo isolada não conta |
| Teleportando | ciclo de teleporte confirmado ainda em andamento |

O badge único usa somente esses quatro nomes e a prioridade:

`Teleportando > PvP > Farm > Ocioso`.

Boss permanece como sinal auxiliar de proximidade para regras e API, sem criar
outro nome no badge. Farm expira exatamente depois de 30 segundos sem novo dano
ou abate PvE; ganho de EXP isolado não ativa Farm.

### 5.7 APIs de saída

Primeiro contrato mínimo:

- `GET /api/v1/health` — versão, RAM atual/orçamento/pressão, estado da captura,
  último checkpoint e contadores permitidos do stream;
- `GET /api/v1/status` — estado agregado por cliente, sinais, idades e
  confiança;
- `GET /api/v1/map` — mapa, posição local e jogadores próximos fornecidos pelo
  Módulo Mapa;
- endpoints adicionais de monitor somente quando houver consumidor aprovado;
- endpoints de leilão pertencem à 2.1.

Regras de segurança:

- bind exclusivo em `127.0.0.1` por padrão;
- Bearer token aleatório, revogável e protegido localmente;
- respostas por cliente, schema versionado e timestamps explícitos;
- respostas limitadas a 256 KiB, 20 requisições/s e quatro conexões simultâneas;
  CORS negado por padrão;
- nenhuma rota de evento bruto, pacote, credencial ou `0x0101`;
- campo desconhecido usa `null`, nunca um `false` inventado.

Integração com o site continua sendo saída autenticada separada; ela não deve
depender da API local estar exposta.

### 5.7.1 Consulta de sessões na rede local

Uma API LAN separada poderá permitir que uma instalação consulte resumos de
sessões de outra instalação na mesma rede. A primeira entrega fica restrita a
EXP, nível, tempo, recursos e combate sanitizados, sem eventos, payloads,
inventário detalhado, mapa ou controle remoto.

O contrato proposto usa consulta pull, endereço manual, pareamento temporário,
TLS com certificado fixado, credencial exclusiva `sessions:read`, ID público de
sessão e paginação. A API local existente permanece em `127.0.0.1`; nenhuma
porta de rede é aberta por esta etapa de planejamento.

**Adicionar cliente** será a entrada única da coleção visual. Além dos clientes
locais já detectados, ela oferece **Externo via API** para selecionar um
computador pareado e um `client_id` público recebido em sua sessão. O cliente
externo aparece junto dos locais com selo de origem e somente capacidades de
leitura; não entra na captura, no Módulo Mapa ou nos bancos locais.

Estado local do candidato: a ação já pergunta **PC local**, **Emulador local**
ou **Externo via API**; as duas origens locais ocupam apenas vagas compatíveis.
Excluir um cliente adicionado remove somente sua entrada visual e desliga seus
monitores selecionados, preservando sessões e dados. Como a LAN ainda não foi
implementada, escolher a origem externa apenas informa a indisponibilidade e
não cria um cliente sem provedor pareado.

Especificação detalhada: `SPEC-SESSOES-LAN-RF-QOL-2.0.md`.

### 5.8 Regras, alarmes e sons personalizados

Criar um único motor de regras consumindo os sinais de estado. Cada regra deve
definir:

- clientes e condições;
- prioridade, cooldown, repetição e recuperação;
- canais: interface, overlay e som;
- motivo e evidência que dispararam o alerta.

Sons personalizados devem ser arquivos locais copiados para uma pasta
controlada do programa, com formato, tamanho e duração limitados. URLs remotas,
scripts e executáveis não são sons válidos. Deve existir teste de volume,
fallback para som padrão e proteção contra repetição contínua.

Drops de itens usam apenas `drop_item_field` com resultado confirmado. Os
índices reservados de EXP, créditos e contribuição não disparam som. A leitura
em memória mantém somente a janela recente e usa a mesma chave sanitizada da
leitura persistida, impedindo que o mesmo drop toque novamente após o
checkpoint no SQLite. Ao abrir uma sessão existente, os eventos recentes viram
baseline silencioso; somente drops posteriores geram alerta.
Na Visão geral, cada drop mostra o ícone do item e usa a cor do `Grade` do
catálogo: Comum, Incomum, Raro, Épico ou Lendário. Item sem grade usa cinza
neutro, sem inferir raridade.

Primeiro conjunto local de regras prontas: ameaça confirmada próxima, transição
para Farm e início de Teleporte, todos usando o mesmo snapshot de estado e um
intervalo mínimo configurável entre 5 e 300 segundos. Isso evita introduzir uma
linguagem de condições arbitrárias antes de existirem prioridades, consumidores
e critérios de recuperação aprovados.

### 5.9 Sessões e uso de memória

Estados de sessão propostos:

`active -> checkpointing -> finalized -> exported/uploaded -> cleanup_eligible`.

Comportamento:

- redutores mantêm em RAM apenas estado atual e janelas necessárias;
- contadores/resumos são gravados em checkpoint periódico e no encerramento;
- a sessão lógica pode continuar enquanto segmentos físicos são fechados por
  tempo, troca de mapa ou limite aprovado;
- um segmento só libera a memória quente após checkpoint confirmado;
- eventos brutos sanitizados ficam opcionais para diagnóstico/captura
  histórica, não obrigatórios para os monitores;
- arquivos e eventos persistidos só são removidos após exportação/upload
  validado ou confirmação explícita conforme política aprovada;
- métricas devem mostrar fila, lag, eventos retidos, âncoras, tamanho do banco,
  segmento atual e motivo de descarte.

O checkpoint local atual é aditivo e idempotente por sessão e último evento:
grava contadores e tamanho persistido depois de cada leitura com eventos novos e
é promovido para `paused` ou `finalized` no encerramento correspondente. Leituras
sem eventos novos atualizam o mesmo ponto em vez de criar crescimento contínuo.

Proteções já implementadas localmente:

- em **Configurações**, o usuário escolhe um orçamento de 256 MiB a 2 GiB, em
  passos de 128 MiB; 768 MiB é o padrão recomendado;
- abaixo de 768 MiB, filas de pacotes, eventos recentes, âncoras, bosses,
  fluxos TCP, segmentos fora de ordem, linhas do Banco PvP, miniaturas,
  cooldowns de alertas e histórico de personagens diminuem proporcionalmente,
  sempre respeitando mínimos funcionais;
- acima de 768 MiB, o valor adicional serve como margem para Qt, Python e
  bibliotecas nativas: coleções internas não ultrapassam os tetos seguros já
  validados, evitando transformar RAM disponível em retenção desnecessária;
- no perfil padrão, o callback do Pktmon nunca bloqueia esperando disco ou
  decoder: cada uma das duas filas admite no máximo 8.192 pacotes e 32 MiB;
  sobrecarga incrementa contadores explícitos de descarte em vez de reter
  memória sem limite;
- no perfil padrão, o reagrupamento TCP mantém no máximo 64 fluxos, 4 MiB de
  buffer contínuo e 256 segmentos/2 MiB fora de ordem por fluxo;
- eventos gerais, bosses, âncoras, identidades, relações de guilda e estado de
  mapa possuem limites estruturais além dos TTLs;
- no perfil padrão, o Banco PvP consulta e cria controles para no máximo 250
  UIDs por vez, somente quando sua aba está visível; filtros consultam o SQLite
  completo;
- no perfil padrão, ícones do inventário são reduzidos para 46 px e mantidos em
  LRU de 256 entradas; cooldowns de alertas e histórico entregue à interface
  também têm limites;
- o Working Set é amostrado a cada 5 s e exibido como **uso / orçamento**;
  acima do orçamento escolhido o programa reduz caches dispensáveis, registra
  diagnóstico e mantém as filas protegidas;
- caches da interface e limite das consultas passam a obedecer a nova escolha
  imediatamente; filas de captura e decoder já ativas adotam o novo perfil na
  próxima ativação, sem interromper a sessão atual de forma inesperada.

O orçamento é uma política de retenção e pressão, não um limite rígido imposto
ao processo pelo Windows. A interface, o interpretador e bibliotecas nativas
também usam memória e podem oscilar. Por isso, uma ultrapassagem persistente do
orçamento é falha de validação e bloqueia release; o programa prefere descartar
pacotes sob sobrecarga, com contadores visíveis, a crescer sem limite ou falhar
por falta de memória.

Depois de gerar o executável candidato, o gate prolongado pode ser registrado
sem controlar a interface:

`python tools/memory_soak.py --pid <PID> --hours 10 --interval 30 --budget-mib 256 --output memory-soak-256.csv`

O arquivo CSV é gravado a cada amostra e o resumo final informa pico, valor
final, tendência das quatro horas finais e aprovação/reprovação. O processo do
RF QOL continua sob controle exclusivo do usuário durante o ensaio.

O intervalo de segmentação e o prazo de retenção não devem ser fixados antes de
medir uma sessão real prolongada.

### 5.10 Definição automática da subsessão por proximidade

Adicionar uma opção por cliente para **preencher automaticamente mapa, spot e
mobs da subsessão ativa**. A subsessão continua podendo ser iniciada sem esses
detalhes; o preenchimento acontece depois, quando houver evidência estável:

- mapa e coordenadas vêm do `MapState` do mesmo `client_key`;
- spot é resolvido por catálogo espacial versionado, usando polígono ou raio
  aprovado dentro do mapa confirmado;
- mobs vêm das aparições PvE próximas do mesmo cliente, mapa e janela de tempo,
  não da lista completa de mobs cadastrados para o mapa;
- cada campo registra valor, origem (`automatic` ou `manual`), confiança,
  `observed_at` e versão do catálogo;
- mapa/spot exigem permanência mínima e histerese antes da confirmação; mobs
  exigem observações repetidas na janela para reduzir aparições de passagem;
- dado desconhecido permanece `null/pendente` e nunca reutiliza o último mapa,
  spot ou conjunto de mobs de outra subsessão;
- edição manual sempre prevalece e bloqueia nova alteração automática daquele
  campo até o usuário reativar a inferência;
- um cliente sem uma das duas vagas do Módulo Mapa mostra automação de contexto
  indisponível, mas continua permitindo edição manual e coleta de EXP.

No primeiro ciclo, a automação apenas define os detalhes da subsessão já ativa.
Encerrar e abrir outra subsessão automaticamente por troca estável de mapa/spot
deve ser uma opção separada e só entra após validar permanência, portais,
instâncias e oscilações nas bordas dos spots. Toda alteração automática fica
auditável e pode ser corrigida sem alterar os eventos originais.

### 5.11 Aba Ranking de EXP — Top 100 do servidor

Criar uma aba independente **Ranking de EXP** para reproduzir o **Top 100
oficial do servidor** capturado passivamente. Ela não usa, compara ou agrega
EXP das sessões e subsessões locais.

Fonte confirmada para integração futura:

- `0x1A01` informa `start_index` e `requested_count` da página solicitada pelo
  cliente do jogo;
- `0x1A02` devolve registros com `rank`, `previous_rank`, `total_exp`, nome do
  personagem, guilda e campos brutos de escopo/ciclo;
- `0x1A03`/`0x1A04` fornecem a consulta e a informação individual do ranking;
- os layouts estão confirmados no decoder de análise e o parser portado integra
  o baseline local no commit `8961824`;
- `scope_id_raw` e `ranking_cycle_raw` continuam brutos até a semântica de
  servidor/ciclo ser confirmada por capturas correlacionadas.

Regras do snapshot:

- a captura continua passiva: o programa observa as páginas que o cliente do
  jogo consultar e nunca gera pedidos de ranking;
- páginas são agrupadas somente quando pertencem ao mesmo servidor, escopo,
  ciclo e janela de captura;
- duas observações idênticas vindas dos Clientes A/B são deduplicadas e
  reforçam a mesma evidência, sem duplicar posições;
- o estado `complete` exige exatamente as posições únicas `1..100` do mesmo
  contexto; qualquer ausência, repetição ou conflito mantém o estado `partial`;
- snapshot parcial pode ser exibido como **Parcial N/100**, com faixas
  observadas, posições ausentes, captura e idade claramente visíveis;
- posições ausentes nunca são completadas com registros de outro servidor,
  ciclo ou snapshot antigo;
- um snapshot completo só substitui o anterior de forma atômica; páginas novas
  ficam em staging até formar contexto coerente;
- sem identificação confirmada do servidor, o snapshot permanece isolado como
  `server=unknown` e não recebe nome presumido.

A aba mostra posição, variação fornecida pelo servidor, personagem, guilda,
nível e percentual derivados da EXP total com a curva 1.28.5, e a EXP total
oficial, além de servidor, ciclo quando confirmado, data da captura,
idade e completude. Deve possuir busca por personagem/guilda e destacar dados
vencidos. Não mostrar EXP/h, percentual/h, mapa, spot, mobs ou qualquer métrica
derivada de subsessão.

UIDs de personagem/Profile, marca de guilda bruta, payload e campos ainda não
interpretados não aparecem na interface, logs comuns ou APIs. Uma futura
`GET /api/v1/server-exp-ranking` poderá expor o snapshot sanitizado, incluindo
completude e staleness, somente após consumidor e política de retenção serem
aprovados. Envio ao site continua sendo integração separada.

Implementação local iniciada:

- spec escopada em `SPEC-RANKING-EXP-TOP100-RF-QOL-2.0.md`;
- snapshots limitados às posições 1–100, com janela de 15 minutos,
  deduplicação, conflitos e completude explícita;
- snapshot parcial visível localmente como `Parcial N/100`;
- envio automático permitido somente quando o snapshot estiver completo;
- aba local com busca e sem UIDs ou campos brutos;
- sem instalador, publicação, release, deploy ou mudança no site de produção.

### 5.12 Licença 2.0

A política da 2.0 separa quantidade de clientes de autorização funcional:

- remover cotas de PC, emulador e cliente externo da licença;
- manter `features` assinadas e gate de licença no núcleo de cada módulo;
- elevar a tolerância offline máxima para 7 dias;
- tentar revalidar uma vez em toda abertura do programa;
- sucesso online emite nova janela assinada; abertura offline nunca reinicia o
  prazo localmente;
- remover o ciclo obrigatório de revalidação de 24 horas;
- verificar `valid_until` durante a execução e bloquear módulos quando vencer;
- resposta explícita de revogação bloqueia imediatamente;
- timeout/5xx permite somente o restante da janela já assinada;
- limites de RAM, concorrência, captura e as duas vagas do Módulo Mapa continuam
  técnicos, não comerciais.

As sete features aprovadas, em ordem canônica, são:

1. `base` — núcleo, captura passiva, clientes, sessões, EXP/recursos locais,
   inventário, Mercado, Codex, Coleção, Memory Chips, status/alertas/sons e APIs
   básicas;
2. `monitor-pve` — Monitor e Banco PvE, HP/localizações, sincronização e contexto
   de mobs;
3. `monitor-pvp` — Monitor PvP e a compatibilidade do Banco PvP na 2.0;
4. `monitor-boss` — Monitor Boss, vida, DPS, ranking de dano e overlays;
5. `map` — mapa, coordenadas, proximidade, API `/map` e contexto espacial;
6. `sessions-lan` — consulta sanitizada de sessões e **Externo via API**;
7. `exp-ranking` — captura, integridade, aba e API do Top 100 oficial de EXP.

`base` é obrigatória; as outras são opcionais. Status, regras, alarmes, sons e
APIs compartilhados não contornam o gate: um sinal ou dado derivado exige também
a feature que o produz. A automação de subsessão exige `map` para mapa/spot e
`monitor-pve` para mobs. `sessions-lan` libera apenas o resumo remoto aprovado,
sem liberar telas ou detalhes dos monitores.

A mudança deve usar lease v3. A lease v2 continua normativa para clientes 1.x e
não será reinterpretada. O contrato, migração, estados, segurança e rollback
estão em `SPEC-LICENCA-RF-QOL-2.0.md`.

## 6. Estrutura de interface proposta

Reduzir a navegação sem esconder funções:

- **Visão geral** — estado principal, clientes, localização, sessão e alertas;
- **Monitoramento** — abas PvE, PvP e Boss;
- **Bancos** — abas PvP, PvE e Leilão;
- **Sessões** — atual, segmentos, histórico e limpeza;
- **Rankings** — Top 100 oficial de EXP do servidor;
- **Integrações** — site, API local e saúde;
- **Alertas** — regras e sons;
- **Configurações** — captura, idioma dos dados e preferências.

O painel de licença da 2.0 mostra módulos liberados, resultado da tentativa
desta abertura, prazo offline e **Tentar validar agora**. Ele não mostra nem
aplica quantidade de clientes e não anuncia próxima validação em 24 horas.

O redesenho visual foi aplicado depois dos contratos funcionais. Critérios:
menos cartões simultâneos, ações principais visíveis, filtros persistentes,
estado vazio claro, densidade controlada e acessibilidade.

Estado local atual: **Monitoramento** agrupa PvE, PvP e Boss com licença por
aba; **Bancos** agrupa PvP, PvE e Leilão; **Sessões** reúne sessão atual/envios e
histórico/subsessões; **Integrações** reúne Profile, API local e saúde
sanitizada. A Visão geral segue o mockup aprovado e passou por comparação Qt
automática; a aprovação manual do owner permanece pendente.

## 7. Roadmap por fases

### F0 — Evidência e baseline

- registrar como baseline o contrato confirmado do decoder `0608bd5` e seus
  testes de movimento, warp e saída do alcance;
- validar catálogo de nomes de mapa, staleness, cardinalidade espacial e
  contrato de privacidade da API;
- validar catálogo espacial de spots e janelas de proximidade;
- validar isoladamente o parser `0x1A01`–`0x1A04` que apareceu nas alterações
  paralelas locais, sem incorporá-lo por consequência deste plano;
- validar em capturas reais a paginação `0x1A01`/`0x1A02`, a formação das
  posições `1..100` e a semântica de servidor/escopo/ciclo do Ranking de EXP;
- manter como backlog 2.1 as capturas marcadas de leilão necessárias para fechar
  a reconciliação de estados;
- manter medições automáticas de RAM, fila, banco e latência durante o
  desenvolvimento do código-fonte;
- somente após gerar o executável candidato, medir RAM, fila, banco e latência
  em sessão prolongada e executar o gate Windows de 10 h com dois clientes,
  captura, alertas e
  monitores ativos nos orçamentos de 256 e 768 MiB: após 30 min de aquecimento,
  o Working Set deve respeitar o orçamento escolhido e a tendência nas quatro
  horas finais não pode exceder 10 MiB/h; ultrapassagem persistente, crash ou
  ausência de métricas de descarte bloqueia release;
- simular um terceiro cliente para validar o limite do Módulo Mapa sem afetar
  captura, EXP ou monitores independentes;
- aprovar contratos de estado, flush e privacidade. O baseline de retenção PvP
  foi retirado do gate da 2.0 e transferido para a 2.1.

Gate: owner aprova decisões abertas e critérios mensuráveis.

### F1 — Núcleo de estado e ciclo de sessão

- barramento interno único e redutores versionados;
- dimensões de estado, checkpoints e métricas: implementados; política de
  segmentação física/retenção aguarda o baseline real posterior ao executável;
- checkpoints periódicos, de pausa e finalização: implementados e cobertos pela
  suíte automática local;
- proveniência, confiança e histerese da subsessão implementadas; snapshots
  paginados/deduplicados do ranking por servidor, escopo e ciclo;
- migração aditiva das bases com backup e rollback desenhados.

Gate do código-fonte: testes de contrato automáticos. O ensaio prolongado real
pertence à validação posterior do executável candidato.

### F2 — Módulo Mapa e API base

- `MapState` independente, limitado a dois clientes simultâneos;
- vagas explícitas e estado `capacity_limit` para o terceiro cliente, sem
  substituição silenciosa;
- resolução de mapa, posição local, jogadores próximos e saída do alcance;
- `health` e `map` locais, com autenticação, limites e testes de vazamento:
  implementados e cobertos pela suíte automática;
- contrato de envio remoto preparado, mas desativado até aprovação do destino.

Gate: revisão de segurança/privacidade e aprovação específica da API Mapa.

### F3 — Status, regras e alarmes

- `status` local consumindo o mesmo estado do Módulo Mapa e dos monitores;
- regras prontas de Ameaça, entrada em Farm e Teleporte, cooldown e sons:
  implementadas localmente;
- editor genérico, prioridades e recuperação avançada: pendentes de critérios;
- autenticação, limites e testes de vazamento.

Gate: revisão de segurança e aprovação específica da API local.

### F4 — Monitores e subsessões automáticas

- aba PvE somente com alvo atual; Visão geral com mobs próximos deduplicados,
  nível e HP máximo, sem alvo ou HP atual;
- snapshot PvP de 10 s sem limpar o stream;
- integração dos monitores com o mesmo estado usado pela API e pelos alertas;
- preenchimento opcional de mapa, spot e mobs na subsessão ativa, com
  confiança, histerese, auditoria e prevalência da edição manual: implementado
  e coberto por testes automáticos;

Gate do código-fonte: testes automáticos de isolamento e capacidade. A validação
real simultânea com dois clientes será feita após gerar o executável candidato.

### F5 — Banco PvE; compatibilidade PvP e Leilão

- interface local agrupada com abas PvP, PvE e Leilão: concluída localmente;
- consulta do Banco PvE com HP confirmado, locais, divergências e estado de
  sincronização: concluída localmente;
- vendas próprias do personagem selecionado, sanitizadas e carregadas sob
  demanda: concluídas localmente;
- quarentena/curadoria PvP com preview e promoção conservadora: concluída e
  coberta pela suíte automática local;
- índice aditivo para as consultas por curadoria e status: concluído;
- Banco PvP congelado funcionalmente na 2.0; retenção, limpeza e novas regras
  pertencem ao backlog 2.1;
- delta/ack do Banco PvE, múltiplas localizações e tratamento de HP divergente:
  concluídos no programa e no código do site, sem deploy;
- Banco de Leilão congelado funcionalmente na 2.0; banco do site, API,
  coordenação autenticada da guilda e anti-undercut pertencem ao backlog 2.1.

Gate: migração do Banco PvE validada localmente. Banco de Leilão, Banco PvP e
deploy do site não compõem o gate da 2.0.

### F6 — Reestruturação visual e hardening

- shell e Visão geral portados para o mockup 2.0, com cartões alimentados por
  dados reais e Subsessão ativa permanente no lugar do cartão de sessão/Farm:
  concluídos localmente;
- Monitoramento consolidado em abas PvE, PvP e Boss, mantendo gates de licença:
  concluído localmente;
- consolidação de Sessões e Integrações: concluída localmente e coberta por
  testes automáticos;
- aba Ranking de EXP com Top 100 oficial, completude e staleness explícitas;
- testes automáticos de acessibilidade, telas vazias, escalas e isolamento de
  dois clientes durante o desenvolvimento;
- no executável candidato: ensaio real com dois clientes, sessão de 10 h,
  atualização/migração, rollback e todas as validações manuais.

Gate do código-fonte: suíte automática e autoteste do executável aprovados. O
gate seguinte começa pelo ensaio real e pela aprovação manual/visual do owner.
Instalador, publicação e deploy continuam
separados e exigem autorizações posteriores.

### F7 — Consulta de sessões na rede local

- projeção sanitizada da sessão local, sem rede;
- servidor LAN separado da API loopback, com TLS, pareamento e revogação;
- lista paginada da sessão ativa e de sessões recentes;
- detalhe com EXP, nível, tempo, recursos e combate;
- cliente pull com `ETag`, timeout, backoff e cache limitado;
- coleção que começa com um espaço de cliente e permite adicionar outros sem
  teto funcional predefinido, sem criar thread/cache por cadastro;
- **Adicionar cliente** unifica origem local, emulador e **Externo via API**;
- cliente externo referencia `device_id + client_id` opacos, mostra sua origem
  e permanece somente leitura;
- detalhe vivo somente do externo selecionado e fila escalonada para os demais;
- cadastro persistido e lista paginada/virtualizada, mantendo apenas a página
  visível em widgets;
- pareamento de computadores em Integrações e clientes externos na coleção
  comum e em Sessões;
- testes automáticos de isolamento, vazamento, muitos cadastros, concorrência
  fixa e memória.

Estado: somente especificado. Gate: confirmar o recorte com o owner e obter
autorização específica antes de implementar ou criar regra de firewall. O
ensaio manual entre computadores ocorre apenas no executável candidato.

### F8 — Licença 2.0 e lease v3

- remover `connection_limits` do contrato e de todos os pontos de enforcement;
- manter gates de `features` em interface, atalhos, overlays e operações
  internas;
- substituir `next_check_at` pela tentativa única em toda abertura;
- aceitar cache assinado por até 7 dias, sem extensão local;
- bloquear módulos em `valid_until`, inclusive com o programa aberto;
- preservar `/api/v2` e clientes 1.x;
- implementar `/api/v3`, introspecção dual, estado aditivo e migração/rollback;
- atualizar mensagens para módulos e prazo offline, sem contagem de clientes;
- implementar a ordem canônica `base`, `monitor-pve`, `monitor-pvp`,
  `monitor-boss`, `map`, `sessions-lan`, `exp-ranking` e rejeitar chave
  desconhecida, duplicada ou fora de ordem;
- cobrir limites, revogação, 429, indisponibilidade, relógio e migração com
  testes automáticos.

Estado: cliente, emissor v3 e consumidor dual do site implementados e cobertos
por testes automáticos. O serviço do emissor em staging foi recriado com chave
v3 isolada, respondeu saudável e publicou o `key_id` esperado, sem mudança de
produção. Staging integrado do site, chave definitiva, cutover, executável e
publicação exigem gates separados.

## 8. Critérios de aceite do programa 2.0

- nenhum módulo cria decoder ou captura paralela;
- Módulo Mapa mantém estados independentes por cliente e atualiza posição local
  e jogadores próximos pelos eventos confirmados;
- Módulo Mapa nunca mantém mais de dois clientes ativos; o terceiro recebe
  estado explícito de capacidade sem herdar dados nem interromper outros
  módulos;
- resposta de teleporte troca o mapa, warp atualiza a posição sem reaproveitar
  o campo refutado, e saída do alcance remove a entidade sem esperar o TTL;
- `GET /api/v1/map` devolve schema versionado, staleness e confiança sem dados
  sensíveis;
- memória quente deixa de crescer com a duração total da sessão; filas, fluxos,
  segmentos TCP, eventos, âncoras, widgets e caches possuem tetos testáveis;
- a preferência de RAM persiste entre aberturas, apresenta os limites derivados
  antes de salvar e nunca eleva as coleções internas acima do perfil seguro;
- após gerar o executável candidato, os gates reais de 10 h respeitam os
  orçamentos de 256 e 768 MiB, com tendência
  nas quatro horas finais de no máximo 10 MiB/h; qualquer ultrapassagem
  persistente bloqueia release, mesmo sem crash;
- checkpoint libera o segmento anterior sem perder resumo ou estado atual;
- PvP atualiza a lista por snapshot de 10 s sem atrasar alvo/ataque crítico;
- Monitor PvE não mostra próximos, mas Banco PvE continua recebendo evidência;
- observação idêntica de mob já confirmada gera zero reenvio;
- o mesmo monstro pode ter múltiplas localizações preservadas sem duplicação por
  pequenas variações de coordenada;
- localização nova ou alterada entra no delta do Banco PvE e recebe ack do site;
- HP divergente não substitui valor canônico sem evidência/revisão;
- a 2.0 não altera nem limpa automaticamente o Banco PvP; decisões manuais e
  compatibilidade existentes permanecem preservadas;
- a projeção local de leilão já existente não envia identificadores sensíveis;
  banco, API, reconciliação compartilhada e anti-undercut são critérios da 2.1;
- status e API distinguem `false` de `unknown/null`;
- API local não escuta fora do loopback e não expõe eventos brutos;
- API LAN, quando autorizada, é um servidor separado, desligado por padrão,
  limitado à interface privada escolhida e ao escopo `sessions:read`;
- sessões remotas usam IDs opacos e nunca expõem `session_id`, UID, fluxos,
  portas, payload, credenciais ou `0x0101`;
- o visualizador não replica o banco remoto e não mistura métricas de origens
  diferentes;
- a interface começa com um espaço de cliente e permite adicionar outros sem
  teto funcional predefinido;
- **Adicionar cliente** inclui explicitamente **Externo via API**, além de
  cliente local e emulador;
- o mesmo externo não pode ser adicionado duas vezes com o mesmo
  `device_id + client_id`;
- cartão externo mostra origem e somente leitura; ações locais não são
  executadas contra ele;
- aumentar a quantidade de clientes cadastrados não cria uma thread, conexão ou
  cache vivo por cliente e não ultrapassa a concorrência derivada do orçamento
  de RAM;
- a lista de clientes remotos não instancia todos os cartões/widgets de uma vez;
- licença 2.0 não contém nem aplica cota de PC, emulador ou cliente externo;
- todo módulo protegido exige lease válida e feature correspondente também em
  atalhos, overlays, workers e chamadas diretas;
- a lease v3 aceita somente as sete features aprovadas, em ordem canônica, com
  `base` obrigatória e sem desbloqueio indireto entre módulos;
- toda abertura tenta revalidar uma vez, mesmo com comprovante recente;
- falha de rede mantém módulos somente até o `valid_until` assinado, nunca além
  de 7 dias desde a última validação online;
- abrir novamente sem sucesso não reinicia a janela offline;
- o vencimento durante a execução encerra com segurança as operações protegidas
  e bloqueia os módulos;
- clientes 1.x e `/api/v2` permanecem compatíveis durante a migração v3;
- alarmes respeitam prioridade/cooldown e nunca executam conteúdo do usuário;
- alerta de drop ignora recompensas não-item, não repete o mesmo evento após
  persistência e funciona durante captura ativa sem exigir a ativação de um
  monitor de combate;
- mapa e coordenadas apresentados vêm do contrato confirmado do decoder e de
  catálogo versionado;
- automação da subsessão preenche somente evidência estável do mesmo cliente e
  mantém `null` quando mapa, spot ou mobs não estiverem confirmados;
- correção manual prevalece sobre inferência automática e fica auditável;
- Ranking de EXP usa somente as respostas oficiais `0x1A02` do servidor e não
  deriva valores de sessões ou subsessões;
- Top 100 só recebe estado completo com posições únicas `1..100` do mesmo
  servidor/escopo/ciclo; captura incompleta mostra `Parcial N/100`;
- páginas repetidas por dois clientes não duplicam posições e páginas de
  contextos diferentes nunca são combinadas;
- interface e API do ranking não expõem UIDs, payload ou campos brutos;
- migrações possuem backup verificável e rollback ensaiado.

## 9. Riscos principais

1. Índice de mapa ser resolvido com catálogo de outra versão ou permanecer
   associado ao snapshot anterior durante um warp incompleto.
2. Coordenadas de jogadores próximos ficarem antigas por perda do evento de
   saída ou exporem mais informação do que o consumidor autorizado precisa.
3. Pequenas variações de coordenada criarem cardinalidade excessiva no Banco
   PvE se a tolerância espacial for estreita demais.
4. HP do mesmo `npc_index` variar por dificuldade/instância e ser sobrescrito
   como se fosse um valor único.
5. Heurística anti-bot remover jogador real ou apagar decisão da guilda.
6. Flush literal perder identidade/eventos e reproduzir o problema de presença
   antiga do PvP.
7. API ou sincronização revelar dados além do contrato sanitizado.
8. Segmentação encerrar sessão antes do checkpoint durável.
9. Na 2.1, o Banco de Leilão ficar desatualizado quando o membro não abrir a
   própria lista de vendas.
10. Redesenho da UI ocultar controles críticos ou reduzir a legibilidade dos
   monitores.
11. Um terceiro cliente ocupar ou herdar indevidamente a vaga/dados de um dos
   dois clientes ativos do Módulo Mapa.
12. Oscilação perto da borda de um spot alterar repetidamente a classificação
   automática ou fragmentar subsessões.
13. Mobs apenas de passagem serem atribuídos ao spot, ou correção manual ser
   sobrescrita por nova inferência.
14. Ranking de EXP combinar páginas de servidores/ciclos distintos, apresentar
   Top 100 parcial como completo ou manter snapshot antigo sem aviso.
15. UIDs e campos brutos presentes no protocolo do ranking escaparem para UI,
   logs, API ou integração do site.
16. Janela offline de 7 dias atrasar a percepção de uma revogação enquanto o
    computador permanecer sem conexão.
17. Tentar validar em toda abertura gerar excesso de chamadas em ciclos de
    falha/reabertura se cliente e emissor não aplicarem timeout e rate limit.
18. Remover cotas de clientes remover acidentalmente também os gates de feature
    dos módulos.
19. Migrar a lease em lugar da evolução aditiva quebrar clientes 1.x ou o
    rollback do executável.

## 10. Decisões e gates do owner

1. Resolvido para a 2.0: o ciclo de 10 s vale somente para próximos; alvo atual
   e ataque crítico continuam imediatos.
2. Adiado para a 2.1: Banco de Leilão terá apenas listagem capturada ou também
   intenção manual?
3. Adiado para a 2.1: quem vê e edita os anúncios da guilda: membro, líder ou
   ambos?
4. Adiado para a 2.1: política de idade, compactação e remoção de observações
   PvP sem guilda/revisão.
5. Quais consumidores receberão a API Mapa e existe destino remoto/site além
   do acesso local?
6. Quais campos de jogadores próximos podem sair do programa e por quanto
   tempo podem ser retidos?
7. Resolvido para a primeira entrega: bucket espacial versionado de 1 unidade;
   recalibrar somente com evidência real posterior ao executável.
8. Resolvido para a 2.0: Farm mantém janela de 30 segundos e o badge usa
   `Teleportando > PvP > Farm > Ocioso`; Boss permanece sinal independente.
9. Qual política de segmentação e retenção de sessões será adotada após o
   baseline prolongado?
10. Resolvido para a 2.0: as vagas do Módulo Mapa ficam com os dois primeiros
    clientes até a rota ser liberada; o terceiro recebe `capacity_limit`.
11. Resolvido para a primeira entrega: a automação apenas preenche a subsessão
    ativa; não encerra nem abre outra por troca de mapa/spot.
12. Resolvido para a primeira entrega: três leituras coerentes por pelo menos
    cinco segundos, com filtro de mobs transitórios; recalibrar somente após
    evidência real.
13. Resolvido para a primeira entrega: exibir snapshot parcial com
    `Parcial N/100`; somente o completo pode seguir para envio automático.
14. Resolvido para a primeira entrega: somente snapshot local mais recente; a
    retenção histórica e novos destinos de site/API permanecem gates externos.
15. Resolvido para a primeira entrega LAN: começar com um espaço de cliente e
    permitir que o usuário adicione outros sem teto funcional predefinido;
    concorrência e memória continuam limitadas pelo perfil escolhido.
16. Resolvido para a primeira entrega LAN: o cliente externo recebido pela API
    deve aparecer na mesma opção **Adicionar cliente** dos clientes locais.
17. Consulta LAN: confirmar endereço manual e pareamento como primeira entrega,
    deixando descoberta automática para depois.
18. Consulta LAN: confirmar sessão ativa mais 20 concluídas recentes e nome do
    personagem sem UID.
19. Consulta LAN: confirmar recursos como deltas de créditos, contribuição e
    loot, mantendo diamantes como saldo atual explicitamente rotulado.
20. Resolvido para a 2.0: nenhum cliente PC, emulador ou externo consome cota de
    quantidade da licença.
21. Resolvido para a 2.0: módulos continuam exigindo lease válida e feature
    correspondente em todas as superfícies.
22. Resolvido para a 2.0: tolerância offline máxima de 7 dias, sem extensão
    local por reabertura.
23. Resolvido para a 2.0: tentar revalidar uma vez em toda abertura e retirar o
    ciclo obrigatório de 24 horas.
24. Resolvido para a 2.0: a lease v3 usa uma chave Ed25519 exclusiva com
    `key_id` próprio; a chave v2 permanece destinada aos clientes 1.x. Gerar ou
    promover a chave definitiva de produção continua sendo gate separado.
25. Resolvido para a 2.0: usar, em ordem canônica, `base`, `monitor-pve`,
    `monitor-pvp`, `monitor-boss`, `map`, `sessions-lan` e `exp-ranking`, com o
    mapa funcional definido em `SPEC-LICENCA-RF-QOL-2.0.md`.

### 10.1 Escopo adiado para a 2.1

- evolução funcional do Banco PvP;
- política de idade, retenção, compactação e limpeza;
- qualquer automação sobre quarentena ou Banco Final além do comportamento já
  existente;
- novos contratos de sincronização PvP com o site.
- evolução funcional do Banco de Leilão além da projeção/aba local já existente;
- banco e API do site, coordenação da guilda, intenção manual, visibilidade,
  retenção, permissões e regras de anti-undercut do leilão.

## 11. Revisão multi-cliente

Revisão de planejamento executada com Mistral Small 3.2 e Qwen 3 locais.
Fable ficou indisponível por cota/créditos e não foi contado como parecer.

Convergências aproveitadas:

- separar evidência, núcleo, APIs, monitores, bancos e interface em fases;
- estender o Banco PvE e o decoder de leilão existentes;
- reaproveitar o decoder confirmado de mapa, movimento e teleporte em vez de
  planejar nova descoberta do protocolo;
- manter segmentação de sessão e decisões de TTL como contratos explícitos.

A atualização de Mapa/Banco PvE também foi revista pelos dois modelos. Ambos
concordaram com `MapState` por cliente, API local autenticada, armazenamento
separado de múltiplas localizações, proteção contra staleness e agrupamento
espacial para conter cardinalidade. A primeira entrega fixou bucket de 1 unidade;
fingerprint alternativo e política de campos do envio remoto permanecem gates
externos.

O limite de dois clientes e a definição automática de subsessão receberam nova
revisão dos mesmos modelos locais. Houve convergência em impedir substituição
silenciosa do cliente, mostrar o limite como estado operacional, exigir
estabilidade/histerese na proximidade e fazer a correção manual prevalecer.

A interpretação inicial de ranking local por subsessão foi descartada após a
correção do owner. Mistral Small 3.2 e Qwen 3 revisaram novamente o escopo como
Top 100 oficial do servidor. Ambos convergiram em isolar servidor/escopo/ciclo,
marcar páginas incompletas, deduplicar capturas dos dois clientes, explicitar
staleness e remover UIDs/campos brutos das saídas.

A decisão posterior do owner preserva essa análise do leilão apenas como
referência e transfere sua evolução funcional da 2.0 para a 2.1.

Sugestões rejeitadas na consolidação:

- aumentar TTL de eventos sem baseline;
- priorizar Farm acima de PvP/ameaça;
- identificar ou excluir bots automaticamente por heurística;
- tratar flush como limpeza do estado interno;
- criar endpoint externo para escrever localização no módulo;
- remover todo identificador efêmero também do contrato local, o que impediria
  correlação confiável entre movimento, aparição e saída do alcance;
- expulsar automaticamente um cliente ativo quando um terceiro aparecer;
- abrir uma nova subsessão a cada oscilação de mapa/spot sem janela estável;
- derivar o Top 100 a partir de `gain_exp` ou das subsessões locais;
- preencher posições ausentes com páginas antigas ou de outro servidor/ciclo.

Essas sugestões poderiam aumentar retenção, atrasar alertas críticos ou apagar
jogadores reais. O plano consolidado mantém quarentena/revisão, snapshots
atômicos e prioridade de segurança.

## 12. Próximo gate

O escopo que depende apenas do código local está implementado e validado pela
suíte automática: estado/API/regras, memória/checkpoints, monitores, Banco PvE,
Módulo Mapa/API, subsessão automática, Ranking de EXP Top 100 e interface.

Com o executável candidato já gerado, a ordem restante é:

1. executar nele o ensaio real de 10 h nos perfis de 256 e 768 MiB;
2. validar simultaneamente dois clientes e o limite do terceiro no Módulo Mapa;
3. realizar todas as validações manuais e visuais;
4. somente então decidir sobre instalador, publicação, release e deploy, cada um
   com autorização separada.

Esses ensaios reais/manuais não bloqueiam o progresso atual do código-fonte,
mas bloqueiam a aprovação final do executável. As pendências externas imediatas
das frentes já implementadas ficam limitadas à política de retenção de sessões,
à política de revisão de HP divergente, ao deploy posterior do contrato PvE e
ao destino remoto das APIs. Banco PvP e Banco de Leilão pertencem à 2.1.

A consulta de sessões na rede permanece em planejamento e ainda não faz parte
do código-fonte concluído. Seu próximo gate é a confirmação do recorte descrito
na seção F7; somente depois disso começa a implementação local e automática,
sem antecipar firewall, executável ou ensaio manual.

A política e o código-fonte da licença 2.0 estão implementados localmente. O
cliente aceita v2 somente como transição, tenta obter v3 uma vez por abertura e
não aplica cotas; o emissor preserva v1/v2 e expõe v3 com chave separada; o
consumidor do site seleciona introspecção v2/v3 e confirma as features no
resultado assinado pelo emissor. O próximo gate da F8 é validar o site em
staging integrado e a migração/rollback no executável candidato. Produção,
geração/custódia da chave definitiva, cutover e publicação não estão
autorizados.
