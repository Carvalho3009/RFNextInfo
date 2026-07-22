# Fila OFFLINE RF NEXT 1.28.5 — resultado da rodada (fable)

Data: 2026-07-21. Modo: sem captura nova, sem Ghidra runtime, sem controle de tela.
Fontes usadas nesta rodada:

- `rfnext-data.sqlite` (via CSVs já exportados em `exports/`, pois a execução direta de
  `python`/`sqlite3` está bloqueada por permissão neste ambiente não-interativo);
- `libUnreal.so` (sondagem por contagem de strings ASCII; nomes de classe são UTF-16 e
  exigem `read_elf_utf16.py`, que depende de `python` — bloqueado nesta sessão);
- documentos da rodada anterior: `RFNext-Analise-Offline-Ampla-1.28.5.md`,
  `RFNext-Mobs-EXP-Loot-map.md`, `rfnext_frame_decode.py`,
  `auction-live/RFNext-Auction-handlers.md`.

Limitação de ambiente desta rodada: o harness exigiu aprovação (indisponível em modo
autônomo) para qualquer invocação de `python`/`sqlite3` em ambos os shells, e o Grep
não imprime texto casado em binário (bytes nulos). Por isso os **layouts byte-a-byte
inéditos do Job 1** (opcodes 031b… etc.) não puderam ser extraídos do ELF nesta
passagem; ficam como `inferido` e exigem re-execução com `python` liberado. Todo o
restante foi reconstituído dos artefatos legíveis com exemplos concretos.

---

## RFNEXT-1 — Protocolo (opcodes não tratados)

**Confiança geral: média para o mapa opcode→propósito; baixa para o layout de bytes.**

### Esquema de opcode (confirmado — alto)
- Opcode = `uint16` little-endian nos bytes 4–5 do frame decodificado.
- `opcode_group = opcode >> 8`, `opcode_id = opcode & 0xFF` (ver `rfnext_frame_decode.py`).
- Cabeçalho de frame = 6 bytes: `flags(1) | length(2 LE) | sequence(1) | opcode(2 LE)`.
  Corpo começa no offset 6.
- Grupos de jogo `03xx`/`06xx` chegam encapsulados em `FG2C_bundle_message` (`0x010A`):
  corpo = `size(uint16) + concatenação de frames internos`.

### Mapa opcode→propósito (média — corroborado por strings e docs)
Sondas de string ASCII nesta rodada confirmaram a presença das famílias:
`worldboss`/`contribution` (3 ocorrências), `guild_raid`/`party_dungeon` (4),
`mothership`/`schedule`/`explore` (3). Os nomes de classe completos estão em UTF-16.

| Opcode(s) | Propósito (do cliente) | Direção provável |
| --- | --- | --- |
| `031b`/`031c` | status / lista de chefes fixos | FG2C |
| `031e`/`031f` | posição de chefe (stream de movimento) | FG2C |
| `0330`/`0331` | status / lista de random boss | FG2C |
| `0a01`–`0a16` | quests (aceitar, progresso, alvo, recompensa) | FL2C |
| `0c01`–`0c04` | fases/gatilhos de mapa (mapcontent) | FL2C |
| `0c05`–`0c0a` | world boss: HP, contribuição, ranking | FL2C |
| `0c0b`, `0c11`–`0c16` | guild raid / party dungeon | FL2C |
| `1702` | agenda de conteúdos | FL2C |
| `1802`/`1803` | maior grau de dungeon concluído | FL2C |
| `1805`/`1806` | agenda de chefes | FL2C |
| `1809`/`180a` | população de conteúdo | FL2C |
| `1814` | agenda da Nave-Mãe (Mothership) | FL2C |
| `2301`/`2302` | exploração de mapa | FL2C |

### Suposições
- Convenção `03xx` = mensagens de jogo (id_Game/id_Skill) que trafegam em bundle;
  `0a/0c/17/18/23xx` = mensagens de lobby/UI (FL2C) fora do bundle. Baseado no
  padrão já confirmado (`0307` appear/exp, `0316` dying, `06xx` skill, `010A` bundle).
- Pares `NN`/`NN+1` são tipicamente `list`/`update` (snapshot completo vs. delta), como
  no par appear-list/update já visto.

### Tipos/unidades por analogia (INFERIDO — baixo)
Para os opcodes de chefe/HP, os campos previstos, por analogia às mensagens já
confirmadas (`appear_monster_list`, `do_damage`, `update_exp`):
- `m_UID`: `uint32`; `m_NpcIndex`: `uint32` (liga ao catálogo `RF_NPCTable`);
- `m_MaxHP`/`m_CurrentHP`: `int64` (unidade = pontos de HP; ver `do_damage` `<IiqB`);
- `m_Position`/`m_Direction`: `float32` (×3 para posição), coordenadas de mundo;
- contribuição/ranking: `uint32`/`int64`; contadores de fase: `uint16`;
- timers de agenda: `uint32`/`int64` em ms ou epoch-segundos (ver §Job 4).

### Exemplos (formato de frame, INFERIDO para 031x)
Não há payloads capturados para estes opcodes nesta rodada. Estrutura de frame para
qualquer um deles (ex.: `031b`), byte-layout do corpo pendente de `read_elf_utf16.py`:
```
80|len_lo len_hi|seq|1b 03|<corpo>       # ofuscado (flag bit7) — decodificar antes
00|len_lo len_hi|seq|1b 03|<corpo>       # claro
```
Exemplos de mensagens do mesmo transporte **já confirmadas** (bom molde de campos):
```
appear_monster_list 0x0307: count(u16) + N×83B "<IIQIQQfffBfBfffBIIQ"
do_damage           0x061A: "<IiqB" = UID(u32) Damage(i32) CurrentHP(i64) UnitState(u8)
update_exp          0x0307: "<HHHHqq" = action highest before level exp(i64) gain(i64)
```

**Ação para fechar em alto:** rodar `read_elf_utf16.py` sobre `libUnreal.so` para extrair
as classes UTF-16 `FL2C_*`/`FG2C_*` desses opcodes e os serializadores associados.

---

## RFNEXT-2 — Mobs / loot

**Confiança: alto para a cadeia estrutural; a chance de drop permanece não confirmada
no cliente (dinâmica de servidor).**

### Cadeia confirmada (alto)
```
RF_NPCTable.RewardIndex
  -> reward_groups(RewardIndex, BoxType, SubGroupIndex)
  -> reward_items(SubGroupIndex, RewardItemIndex, MinValue, EnchantLevel, BiosuitType)
```
- 10.819 NPCs; 2.783 com `RewardIndex`; 2.566 ligados ao item interno `900` (EXP).
- 169.122 relações NPC→item (1.328 itens distintos), 169.074 com nome PT-BR resolvido.
- Todos os `BoxType` alcançados = `ITEM_REWARD_BOX_TYPE_NONE` (49.988 linhas). Não há
  coluna de probabilidade — o caminho nativo em `0x06784d54`/`0x06784f08` só concatena
  `WHERE RewardIndex={0}` e `WHERE SubGroupIndex={0}`, sem sorteio nem peso.

### Tipos/unidades (alto)
- `NPCIndex`,`RewardIndex`,`SubGroupIndex`,`RewardItemIndex`: `int` (chaves).
- `MinValue`: `int` — para item 900 é EXP base; para item 1 é Crédito base; para itens
  normais é quantidade mínima (contador). `EnchantLevel`: `int` (nível de +).
- `BiosuitType`: enum (`BIOSUIT_TYPE_BASE`…) — só relevante para drops de biosuit.
- `Multiplicity`: nº de vezes que o subgrupo aparece (máx. 2); `MultiplicityShareCandidate`
  (ex.: 0.2) **não é chance confirmada** (`ChanceConfirmed=False`).

### Exemplo (NPC 305901 — Guarda de Fronteira Beltran, nível 10)
`RewardIndex 1000000` → 5 subgrupos:
| SubGroupIndex | Item | MinValue | Semântica |
| --- | --- | ---: | --- |
| 1000020010 | 900 EXP | 10 | EXP base |
| 1000010010 | 1 Crédito | 19 | dinheiro base |
| 4000040000 | 5200/5201/5202/5204/5205/5206 (Kits de Upgrade) | 1 | grupo de kits |
| 4010470000 | 270000–270003, 275000–275001… (materiais) | 1 | grupo de materiais |
| 4010590001 / 4010600001 | (variação por NPC) | 1 | grupo extra |

### Finalizadores / bônus / ActionCode 1006 (alto — via captura anterior e enum do ELF)
Enum `eACTION_CODE` (reflexão do ELF):
```
960 KILLED_NPC · 1000 FIELDDROP · 1001 MODE_REWARD · 1002 FIRST_HIT_REWARD
1003 LAST_HIT_REWARD · 1004 FIELDDROP_TEST · 1005 EXP_BY_FINISH_SKILL
1006 EXP_BY_FINISH_ONEKILL
```
- Recompensa por abate chega em `FL2C_drop_item_field` (`0x040A`), corpo
  `ret(u16) + count(u16) + N×"<HIqqqH"` (ret, item_index, count, item_id, gain_total, action_code).
- `update_exp` (`0x0307`, `<HHHHqq`) traz `m_ActionCode` e `m_GainExp(i64)`.
- **1006 = finalizador one-kill → 10× a EXP normal** (5 casos: 163.030 = 10×16.303),
  com crédito/contribuição inalterados (permaneceram `ActionCode 1001`). Skills
  finalizadoras observadas: `1070122` (Lâmina de Força Deadly) e `1080122` (Arma Mortal Blaster).

### Drops com contador mín/máx e "só em modo 1006"
- `MinValue` fornece o piso do contador; não há coluna de máximo no cliente
  (quantidade final é do servidor).
- Não há flag estática que restrinja um item a `ActionCode 1006`; 1006 alterou apenas o
  multiplicador de EXP, não introduziu itens exclusivos na amostra. → `status: inferido`
  de que não existem "itens só-1006" no cliente 1.28.5.

---

## RFNEXT-3 — Progressão / classes

**Confiança: alto para as tabelas estáticas; a fórmula final de dano não fecha offline.**

### Curva de nível (alto)
- `RF_LevelUpTable` cobre 1–200; `PC_NeedExp` monotônico e único por nível.
- Soma EXP níveis 2–100 = 8.860.877.171.309; 2–200 = 3.022.660.132.182.889.
- `PC_GetStatPoint`/`PC_TotalStatPoint` = 0 em todos os níveis (sem pontos primários
  distribuíveis nessa curva). Ganhos tabulares acumulados até 200: ATQ 540, DEF 560,
  HP 52.999, FP 2.665, precisão 572, evasão 858, crítico 563, resist. crít. 666.

### Fórmulas de status (alto — 25 explícitas + 144 de poder de combate)
```
HP máx = VIT×90 + HP_add      FP máx = WIS×3 + FP_add
ATQ físico ← FOR              ATQ de Força ← INT
DEF = DES + DEF_add           Evasão = AGI + Evasão_add
```
Pesos de poder de combate: ATQ/DEF/precisão/evasão ×8; ATQ físico e de Força ×4;
HP ×0,2; FP ×0,6. **Unidades:** atributos são inteiros; taxas derivadas em `stat_types`
usam sufixo `RATE` (percentuais internos). Enum de status confirmado em
`exports/stat_types.csv` (191 tipos; STR/DEX/VIT/INT/WIS/AGI = 1–6; note que o rótulo
PT-BR do índice 5 aparece como "AGI" e o 6 como "Agilidade" — divergência de rótulo, não
de índice).

### Classes / biosuits (alto)
8 famílias (Punisher, Phantom, Enforcer, Psypher, Dreadnought, Technician, Arbiter,
Demolition). Física: 1,2,5,8; Força: 3,4,6,7. 30 biosuits visíveis por classe (Demolition 23).
Orçamento dos 6 atributos primários por grau: **30 / 54 / 96 / 180 / 318–320 / 528**
(graus 1–6). Gap de pontuação entre classes no mesmo grau: fechado, mesmo orçamento por
grau → diferença entre classes vem da distribuição, não do total.

### Skills e encantamento (alto)
- 24 registros principais por classe em `RF_SkillListTable_Biosuit`; 9 skills-pai com até
  3 variantes; fechamento estático = 408 IDs válidos (353 com buff, 256 com dano).
- Skills-pai abrem em nível 1, 12 e 24; as 6 seguintes usam `Skill_GetType=2` (enum sem
  associação numérica segura → `inferido`).
- Enchant de skill (47 grupos, até +12): +1 100%; +2 80/20; +3 65/35; +4 50/50; +5 45/55;
  +6 40/60; +7 35/65; +8–9 30/70; +10 25/40/35; +11 25/30/45; +12 20/30/50
  (sucesso/mantém/rebaixa). Valores preparados até +15 mas `SkillMaxEnchantLv=12`;
  **+13–15 não acessíveis** nesta versão. Aumento mediano do coeficiente de dano 0→+12 = 48,19%.
- Enchant de biosuit: 7 painéis × 7 opções, soma 10.000; curva 100% (1–3) → 55% (40–42).

### Suposições
- "custo médio de evolução por etapa" = moeda tipo 1 (Crédito) das tabelas de enchant/
  aprimoramento; não há custo de EXP para trocar de grau no cliente.
- Escala de buff/debuff por nível = coeficiente de tabela, **não** efeito final (servidor
  aplica mitigação/crítico).

---

## RFNEXT-4 — Eventos / conteúdo

**Confiança: alto para estrutura estática; "ativo agora" é dinâmico (não afirmável).**

### Chefes / world boss (alto)
- `RF_BossSpawn`: 78 colocações, 69 NPCs, níveis 35–123. World bosses principais:
  Vritra 35, Gleba 50, Verme de Pedra 65, EI-01 80, Igna Vritra 95, Blita Gleba 105,
  Ragdion 115.
- Random boss com timer explícito: Fantasma da Cidadela (`4504901`, nível 102),
  `RF_RandomBossSpawn` = 7.200.000–10.800.000 **ms** (2–3 h). Demais random boss sem timer.

### Rakan (alto)
`RF_EventMonsterTable`: 15 regiões de evento, cada uma com **3 etapas**. Cada etapa cria
1 chefe + 10 auxiliares; `DespawnTime=1800` (**s** = 30 min), `SpawnTime` 55–63 (**s**).
Não prova que o evento está ativo.

### Provas Arcanas / masmorras / conflitos (alto)
- 4 graus/mapas de Provas Arcanas; 15 time dungeons (4 marcadas como evento), todas
  `Use_Charge_Time=3600` (**s** = 1 h).
- Guild Raid: 5 graus; recomendação de nível 40/55/65/70/80; participantes 25/35/45/45/45;
  custo moeda 504 = 3k/9k/15k/25k/30k. 6 mapas de conflito, entrada mínima
  45/60/70/70/85/85.

### Tri-Placas Dimensionais (alto — normalização especial)
48 grupos somam exatamente 100.000.000; **`Rate / 1.000.000` = porcentagem**:
- Instável Novus A–C: normais ~8,636% cada, Mecha ~0,455% cada;
- Estável Novus A–C: 11 versões Mecha ~9,091% cada;
- Instável Albern: 4 comuns 23,75% + 4 raras 1,25%;
- Instável Planeta Exterior: 5 comuns 19% + 5 raras 1%.

### Quests (alto)
1.796 quests, 6.822 alvos, 865 links de próxima quest (sem ciclos), cadeia principal de
794 quests, 195 alvos com limite temporal.

### Pesos de spawn normal/stable/unstable e timers
- Spawn estático em `RF_MapInfoTable_Spawn` (7.681 configs) tem `SpawnValue` (contagem
  colocada), **sem** temporizador de respawn de mob comum → respawn normal não
  extraível offline (`status: inferido`).
- "stable/unstable" aparecem no sistema Tri-Placas (Novus/Albern estável×instável), não
  como pesos de spawn de mob de campo.

### Tipos/unidades
- Timers: `RandomBossSpawn` em **ms**; `DespawnTime`/`SpawnTime`/`Use_Charge_Time` em **s**.
- Requisitos de nível/participantes: `int`. Custos de raid: moeda `int` (tipo 504).

---

## RFNEXT-5 — Economia

**Confiança: alto para taxas/estruturas estáticas; preços e listagens vivas são dinâmicos.**

### Craft (alto)
1.086 receitas (abrem no nível 13). As 4 saídas (`Normal/Better/Huge/Fail`) somam 10.000
em todas. 938 sem falha, 148 com chance de falha; 12 com devolução de material. Perfis
mais comuns: 100/0/0/0 (495), 90/10/0/0 (181), 47/3/0/50 (136), 90/7/3/0 (136), 97/0/3/0 (121).
**Unidade:** cada campo é probabilidade em base 10.000 (÷100 = %).

### Alquimia (alto)
15 tiers; pontos 40→10.800; custo 100k→380k Créditos; previsão 50k→130k. 6 taxas somam
10.000. Tier 1 = 15/10/5/50/15/5; Tiers 2–15 = 30/13/2/15/30/10. 90 grupos de recompensa
resolvem; probabilidade interna do item dentro do grupo não é exposta.

### Remodel Prime (alto)
20 categorias em escala 1.000.000: 200.000 sucesso / 800.000 falha (**20%/80%**). Custo
grau 3–6 = 10k/20k/30k/40k Créditos. 530 itens com entrada+saída Prime válidas.

### Desmontagem / dismantle (alto)
```
ItemTable.ItemReward + nível de aprimoramento
  -> ItemTable_Reward.Dismantle_RewardIndex
  -> RewardTableRow.SubGroupIndex -> SubGroupInfoRow.RewardItemIndex
```
5.041 itens com `ItemReward`; 1.919 linhas de recompensa resolvem. 553 itens em blacklist
(venda/descarte/desmontagem/troca).

### Talic (alto)
576 itens, 18 famílias; todos vinculados e fora do leilão. Slots por grau 1–6: 0/1/2/2/3/3.
Custo de equipar: 5k/10k/30k/50k/100k/200k Créditos. Conversão lendária: T1 1 Prisma+200
Diamantes; T2 2+400; T3 4+800. Mítica T1: 8 Prisma+1.600 Diamantes.

### Leilão / exchange (alto para regras estáticas)
- Leilão mundial: 1.688 itens elegíveis (548 no world-group), todos não vinculados;
  piso por item: 10 (1.292 itens), 30 (341), 50 (15), 300 (31), 1.000 (9); faixa de preço
  10–999.999.999; 20 favoritos, 30 registros, 30 resgates, compra máx. 10.
- Guild auction (`exports/guild_auction_settings.csv`): `AuctionStoragePeriod=4320` (**min**
  = 3 dias), `AuctionIncreaseRate=10`, `MaxAuctionRegisterCount=50`, `ResetHistoryTime=8640`,
  fases `CountDown 10s / Bid 20s / Result 10s / Random 2s / FastBid 10s`,
  `EqualSplitMembershipMinValue=1`.
- Protocolo de exchange já 100% decodificado (`rfnext_frame_decode.py`, opcodes `1D02–1D1B`):
  preços chegam como `double` (ex.: `weekly_average_selling_price`, `lowest/highest_price`),
  quantidades como `uint32`, `exchange_index` como `uint64`, tempos como `uint64`.
  Ex. `0x1D17` = `"<HIHddB"` (ret, item_index, enchant, weekly_avg, last_price, server_type).

### Lojas NPC (alto)
152 produtos em 12 lojas; moedas: 44 Crédito, 21 Guilda, 18 N-Token/raça, 16 Aventura,
11 Jogo de Guerra. Recompra: acréscimo 10, prazo 86.400 s, máx. 30 itens; reset 05:00.

### "Valor esperado por item" (prime/dismantle/alquimia/talic)
- Para `prime`/`alquimia`/`craft`, o valor esperado é calculável até o **grupo** de
  recompensa (probabilidades de tier somam 10.000/1.000.000), mas a distribuição
  **dentro** do grupo não é exposta → EV por item final = `inferido`.
- `dismantle` é determinístico (sem roleta no caminho nativo) → EV por item = a própria
  linha de recompensa (alto).
- `exchange`: impacto no fluxo de circulação depende de preços vivos (dinâmico) — não
  afirmável offline.

---

## RFNEXT-6 — Parser técnico (frame decode 1.27/1.28)

**Confiança: alto (fonte `rfnext_frame_decode.py` legível e com self-test).**

### Pipeline de frame (alto)
1. Comprimento do wire: se `header[0] & 0x80`, comprimento vem XOR-desofuscado de
   `header[1..2]` com estado `header[0]^0xEF`; senão, `uint16` LE direto de `header[1..3]`.
2. Rolling XOR: se bit7 setado, cada byte `i≥1` = `cipher ^ state`, `state = cipher ^
   ((-0x11*i) & 0xFF)`; limpa bit7 no byte 0.
3. Se bit6 setado (`0x40`): corpo LZ4-block descomprimido (capacidade `0xFFFF-6`).
4. Cabeçalho de 6 bytes; opcode = `uint16` LE em [4:6]. Bundle `0x010A` = `size(u16)+frames`.

### Pontos frágeis / regressões prováveis 1.27→1.28 (média)
1. **Constante do rolling XOR `-0x11` (0xEF) e o multiplicador por índice.** É o parâmetro
   mais sensível a mudança de versão; se o servidor girar a chave, todo decode falha em
   cascata. Verificar primeiro numa regressão.
2. **Structs de tamanho fixo dependem de padding/ordem exata.** Ex.:
   `appear_monster_list` = 83 bytes/`"<IIQIQQfffBfBfffBIIQ"`; `do_damage` 17B/`"<IiqB"`;
   `ans_use_skill` 74B fixos + 66B/resultado; `ans_use_normal_skill` 42B + 46B/resultado.
   Qualquer campo novo (ex.: um `uint16`/`float` extra) muda o passo do array e o parser
   rejeita por comprimento — **mesmo nome de opcode, tamanho diferente** é o risco #6 do
   enunciado. Mitigação: validar `len(payload) == prefix + count*record` como já é feito.
3. **`0x0307` é sobrecarregado** (appear_monster_list E update_exp compartilham o id de
   identificação externo). O parser desambigua por comprimento (`<HHHHqq` vs.
   `2+count*83`). Se o corpo do update_exp ganhar/perder campos, pode colidir com um
   `count` plausível de appear. Frágil por design.
4. **LZ4 sem verificação de checksum**; offset/length estendidos (`0x0F`/`0xFF`) confiam no
   fluxo. Frame malformado só é pego por limite de capacidade.
5. **Reassembly TCP** (`_merge_tcp_segments`) assume sequências sem wrap de 32 bits e
   descarta sobreposição por corte simples; retransmissões com dados divergentes não são
   detectadas.
6. **Campos de tempo não usados/possivelmente reinterpretados:** `expire_time`,
   `registed_time`, `selling_time`, `StiffEndTick`, `next_usable_skill_time`,
   `ProjectileActivate/DestTime` — tipos `uint64`/`float`; unidade (ms vs epoch-s) só foi
   confirmada para `Precast_Time` (ms). Mudança de unidade entre versões não quebra o
   decode, mas quebra interpretação.

### Tipos/unidades confirmados
- Todos os inteiros multibyte são little-endian. Preços de exchange = `double` (float64).
- Tempos de skill (`Precast_Time`) confirmados em **ms** por pareamento de respostas
  (`ResponseNumber 0`→`1`). HP/dano em pontos (`int64`/`int32`).

### Exemplos de decode (do self-test, alto)
```
0x1D17 25B  "<HIHddB"   -> market price (item, enchant, weekly_avg, last, server_type)
0x0307 24B  "<HHHHqq"   -> update_exp (action, highest, before, level, exp, gain)
0x040A      "<HH"+N×"<HIqqqH" -> drop_item_field
0x0602      74B + N×66B "<...>" -> ans_use_skill (HPDamage, FinalHP)
```

---

## Critérios de aceite — status
- Suposições listadas por job: sim.
- Tipos/unidades por campo: sim (exceto layout inédito do Job 1, marcado `inferido`).
- ≥5 payloads decodificados por caso: atendido para Jobs 2/5/6 (mensagens confirmadas);
  para Job 1 os 5 exemplos são moldes de mensagens do mesmo transporte, pois os opcodes-
  alvo não têm payload capturado nesta rodada offline.
- Confidence por job: declarado.
- Sem prova em dados → `status: inferido`: aplicado (Job 1 layouts, respawn normal,
  EV intra-grupo, "itens só-1006").
