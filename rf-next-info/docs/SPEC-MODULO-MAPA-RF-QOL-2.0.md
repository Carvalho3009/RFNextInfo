# RF QOL 2.0 — Módulo Mapa e saída local

Status: implementação local concluída em código-fonte em 2026-08-16. Sem publicação, instalador ou integração remota.

## Objetivo

Transformar os eventos espaciais já decodificados em um estado sanitizado por cliente, reutilizável pela interface, Banco PvE, subsessões e APIs locais.

## Fontes confirmadas

- `move_player_request` (`0x0301`): posição do personagem local;
- `move_player_update` (`0x0302`): posição de uma entidade pelo UID efêmero;
- `appear_player_list` e `appear_monster_list`: identidade, posição inicial e tipo da entidade;
- `request_teleport_result` (`0x0409`, servidor de jogo): índice de mapa confirmado após resposta bem-sucedida;
- `teleport_response` (`0x0325`, servidor lógico): índice do mapa de destino e coordenada resolvida quando presente;
- `warp_player` (`0x040A`): posição do UID informado; o campo bruto no offset 18 foi refutado como índice de mapa;
- `end_warp_player` (`0x040B`): fim do ciclo de warp local;
- `disappear_unit_list` (`0x030A`): remoção imediata da entidade do alcance.

Nenhuma nova semântica de protocolo ou captura ativa será criada.

## Catálogo localizado

- fonte versionada: `RF_MapTable` e tabelas de strings oficiais da versão
  `1.28.5`;
- cobertura: 508 `MapIndex`, com 496 nomes PT-BR e 504 nomes EN-US;
- o catálogo embarcado guarda somente `MapIndex`, chave textual e os dois
  rótulos; caminhos e demais campos internos da tabela não são distribuídos;
- a preferência PT/EN afeta somente o nome do mapa, mantendo toda a interface
  em português;
- fallback: idioma escolhido, outro idioma e, por último, `Mapa #<índice>`;
- o usuário pode informar manualmente o mapa atual por cliente; essa informação
  é apenas um fallback de nome quando o automático estiver vazio ou limitado a
  `Mapa #<índice>`, nunca desativa nem substitui um nome automático reconhecido;
- a ação **Selecionar mapa atual** abre a lista pesquisável do catálogo, sem
  entrada livre, para identificar o mapa quando o decoder ainda não resolver o
  nome automaticamente;
- o gerador é determinístico e o executável inclui o JSON resultante como dado
  versionado.

## Capacidade

- O Módulo Mapa admite no máximo dois `client_key` simultâneos.
- Os clientes já admitidos mantêm a vaga enquanto a rota continuar presente.
- Um terceiro cliente recebe `map_enabled=false` e `reason=capacity_limit`.
- Quando uma rota admitida desaparece, a vaga é liberada e preenchida pelo próximo cliente detectado.
- O limite não interrompe captura, EXP, inventário ou monitores.

## Plantas, regiões e spots

- o pacote inclui 49 `MapIndex` solicitados: Novus World, Albern Crater Areas
  1/2, Android Junkyard 5F–14F, Secret Nemesis Base 1F–5F, Public Mining Field
  1F–5F, Exclusive Mining Field e os mapas orbitais indicados;
- o manifesto espacial usa a base oficial 1.29.7 e registra, por mapa, planta,
  limites mundiais, idioma, origem e evidência;
- o `MapIndex` de cada andar permanece como identificador técnico da planta,
  mas não cria um mapa separado na interface: Android Junkyard, Secret Nemesis
  Base e os campos de mineração usam o nome do mapa-base e expõem `1F`, `2F`,
  etc. em `region_name`, com `region_confidence=map-index-floor`;
- Novus 101/103 possui 56 regiões encontradas em `RF_RegionTable`: cada uma
  guarda o centro oficial, a caixa dos spawns estáticos e um recorte com margem;
- a região atual é a de centro oficial mais próximo. Isso identifica o spot e
  mantém o rótulo regional sem declarar polígonos ou fronteiras que os dados não têm;
- a visualização abre com a planta inteira, permite ampliar/reduzir zoom,
  arrastar a posição visível e recentralizar pelo botão **Focar personagem**;
- durante a captura ativa, a posição é reprojetada a partir do stream efêmero
  em memória a cada 1 segundo, mesmo com PvE, PvP e Boss desligados; somente o
  último evento espacial por entidade é mantido;
- `region_index`, `region_name`, `region_center` e
  `region_confidence=nearest-official-center` acompanham o estado sanitizado;
- Android Junkyard 5F–14F usa a planta oficial compartilhada do mesmo
  `LevelPath`, validada porque as coordenadas estáticas cabem na mesma geometria;
- variantes 4645/4665/4685 do Public Mining Field 5F reutilizam a planta 4625
  pela mesma correspondência de `LevelPath` e topologia de coordenadas;
- o gerador falha se uma coordenada estática não couber nos limites da planta
  atribuída, impedindo empacotamento silencioso de uma associação incompatível.

## Licenciamento 2.0

- o estado do Módulo Mapa, a aba, `/api/v1/map`, coordenadas, jogadores próximos
  e o preenchimento espacial de subsessão exigem lease v3 ativa e `map`;
- o decoder e a captura compartilhados não são duplicados nem se tornam uma
  segunda cota; sem `map`, o consumidor espacial não publica nem expõe estado;
- `base` continua obrigatória e mantém captura, sessão, EXP e APIs básicas;
- preencher mobs na subsessão ou registrar localização no Banco PvE exige também
  `monitor-pve`; `map` isolada não libera o Banco PvE;
- as duas vagas simultâneas continuam sendo capacidade técnica do módulo, não
  quantidade licenciada.

## Estado público

Cada cliente admitido pode fornecer:

- `client_key` e nome do personagem quando confirmado;
- `map_index` e `map_name` somente quando disponíveis;
- `map_source` distingue `automatic`, `manual_fallback` e `unresolved`;
- posição local `x`, `y`, `z`, horário, idade e staleness;
- estado de warp quando confirmado;
- jogadores próximos com nome, guilda conhecida, posição, distância e horário;
- confiança e motivo explícitos quando ainda não houver dados.

O contrato público não inclui UID de personagem, UID efêmero de entidade, guild ID, campos brutos, payload, token, ticket ou `0x0101`.

## Retenção em memória

- um único movimento local mais recente por fluxo;
- um único movimento/warp mais recente por entidade visível;
- aparições já mantidas pelo stream atual;
- remoção imediata em `disappear_unit_list`;
- expiração de jogadores próximos em 15 segundos, igual ao monitor de presença;
- o estado local antigo permanece visível com `stale=true`, sem fingir atualização.

## API local

- bind exclusivo em `127.0.0.1`;
- Bearer token aleatório protegido por DPAPI;
- desligada por padrão;
- `GET /api/v1/health`, `GET /api/v1/map` e `GET /api/v1/status` somente leitura;
- `/api/v1/map` informa também a versão do catálogo e o idioma de dados ativo;
- `/api/v1/map` inclui a região resolvida e o centro oficial, sem expor tabelas
  internas ou identificadores de entidade;
- tamanho de resposta limitado e sem CORS permissivo;
- nenhum destino remoto nesta entrega.

## Critérios de aceite

- três rotas simultâneas nunca produzem mais de dois estados habilitados;
- um cliente limitado não herda mapa, posição ou jogadores de outro;
- posição local e de jogadores são isoladas pela rota física;
- somente uma resposta de teleporte bem-sucedida atualiza o índice do mapa;
- o fallback manual deixa de ser aplicado assim que o catálogo automático
  resolver o nome, sem exigir ação adicional do usuário;
- o seletor manual lista somente mapas do catálogo e permite filtrar pelo nome;
- os 49 mapas preparados têm planta empacotada e todo recorte de Novus resolve
  para uma das 56 regiões oficiais;
- warp atualiza posição, mas nunca promove o campo bruto refutado a índice de mapa;
- desaparecimento remove o jogador imediatamente;
- snapshots e API não vazam identificadores internos;
- ausência de `map` bloqueia aba, API e operações diretas do módulo sem afetar
  recursos cobertos por `base`;
- o stream mantém cardinalidade limitada durante sessões longas.

## Rollback

O módulo é aditivo e não exige migração. O rollback remove o catálogo e volta
`map_name` para indisponível, sem alterar `map_index`, coordenadas, captura,
decoder, monitores ou bancos existentes.
