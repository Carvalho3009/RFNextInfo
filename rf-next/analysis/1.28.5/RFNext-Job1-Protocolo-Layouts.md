# RF ONLINE NEXT 1.28.5 — Job 1: layouts de protocolo (opcodes pendentes)

Data: 2026-07-22 · Fonte: `libUnreal.so` (AArch64, SHA-256 `da297482…cd51c8d`).
Modo offline: sem captura, sem runtime, sem Ghidra — recuperação estática por disassembly (capstone).

## Resumo

Esta rodada fecha o item que ficou `inferido` no run anterior do fable (o harness autônomo não
pôde executar Python sobre o ELF). Aqui foram recuperados, de forma estática:

- o **catálogo completo** de 1.771 classes de mensagem (`FL2C` 815, `FC2L` 535, `FG2C` 274, `FC2G` 82, `FA2C` 37, `FC2A` 28);
- o **opcode real** de 1.466 dessas classes (imediato do getter de ID na vtable);
- o **layout byte-a-byte** do corpo (formato de serialização) das classes dos opcodes pendentes.

### Como foi obtido (e validado)

Cada classe expõe, adjacente ao nome UTF-16, um getter `mov w0, #<opcode>; ret` (ID da mensagem)
e uma vtable em `.data.rel.ro`. O (de)serializador é alcançado por um thunk `add x1,x0,#K; b <fn>`
ou é concreto; o corpo transfere cada campo entre a struct (`[reg,#imm]`) e o buffer
(`[reg, cursor]`), e a **largura** do load/store dá o tipo. O extrator foi validado contra
três mensagens já confirmadas em captura, com casamento exato:

| Mensagem | Recuperado | Confirmado (rodadas anteriores) |
| --- | --- | --- |
| `FL2C_update_exp` | `<HHHHQQ>` (24 B) | `<HHHHqq>` (24 B) ✓ |
| `FG2C_do_damage` | `<IIQB>` (17 B) | `<IiqB>` (17 B) ✓ |
| `FG2C_appear_monster_list` (registro) | `<IIQIQQfffBfBfffBIIQ>` (83 B) | `<IIQIQQfffBfBfffBIIQ>` (83 B) ✓ |

Tipos: `B`=uint8 `H`=uint16 `I`=uint32 `Q`=uint64 `f`=float32 `d`=float64. A largura é exata;
**a sinalização (signed/unsigned) não é distinguível só pela largura** — ex.: em `do_damage` o campo
`Damage` é `int32` e `CurrentHP` é `int64` embora apareçam como `I`/`Q`. Para mensagens de lista, o
corpo externo traz cabeçalho + contador e o **registro** repetido é a struct indicada em `-> registro`.

## Layouts por opcode pendente

### 031b/031c boss status/list

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `0x031b` | `FG2C_notify_boss_status_Message` | `<IIIIIQQBB` | 38 |  |
| `0x031c` | `FG2C_notify_boss_status_list_Message` | `<BII` | 9 | `<IIIIIQQBB` (38 B) |
| `—` | `FL2C_ans_boss_status_list_Message` | `<BBII` | 10 | `<IIIIIQQBB` (38 B) |
| `—` | `FC2L_ask_boss_status_list_Message` | _(corpo vazio / ask sem payload)_ | — | — |

### 031e/031f boss position

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `0x031f` | `FG2C_ans_boss_position_Message` | `<Ifff` | 16 |  |
| `0x031e` | `FC2G_ask_boss_position_Message` | _(corpo vazio / ask sem payload)_ | — | — |

### 0330/0331 random boss

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `—` | `FG2C_notify_random_boss_status_Message` | `<IIIIB` | 17 |  |
| `0x0331` | `FG2C_notify_random_boss_status_list_Message` | `<BII` | 9 | `<IIIIBB` (18 B) |

### 0a01-0a16 quests

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `0x0a07` | `FL2C_ans_request_quest_Message` | `<HIB` | 7 |  |
| `0x0a0b` | `FL2C_ans_cancel_quest_Message` | `<HIB` | 7 |  |
| `0x0a08` | `FC2L_ask_quest_action_Message` | `<IIIB` | 13 |  |
| `0x0a04` | `FC2L_ask_quest_reward_Message` | _(corpo vazio / ask sem payload)_ | — | — |
| `0x0a13` | `FC2L_ask_quest_update_Message` | _(corpo vazio / ask sem payload)_ | — | — |
| `0x0a0e` | `FC2L_ask_quest_skip_Message` | _(corpo vazio / ask sem payload)_ | — | — |

### 0c01-0c04 mapcontent/phase

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `0x0c01` | `FG2C_map_phase_info_Message` | `<IBBBBIIII` | 24 |  |
| `0x0c03` | `FG2C_map_phase_countdown_Message` | _(corpo vazio / ask sem payload)_ | — | — |
| `—` | `FL2C_mapcontent_noti_Message` | `<BQBII` | 18 |  |
| `—` | `FL2C_ans_mapcontent_result_info_Message` | `<dQQ` | 24 | `<BHBQIIQ` (28 B) |

### 0c05-0c0a world boss

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `0x0c07` | `FG2C_worldboss_hp_sync_Message` | `<IQQBQB` | 30 |  |
| `0x0c08` | `FG2C_worldboss_personal_contribution_update_Message` | `<QQIQ` | 28 |  |
| `0x0c05` | `FG2C_noti_worldboss_result_Message` | `<HI` | 6 | `<IQQQIB` (33 B) |
| `0x0c0a` | `FG2C_ans_worldboss_top_players_info_Message` | `<HQ` | 10 | `<IQQQIB` (33 B) |

### 0c0b/0c11-0c16 guild raid / party dungeon

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `0x0c0b` | `FG2C_guild_raid_round_state_Message` | `<HBII` | 11 |  |
| `0x0d6b` | `FL2C_guild_raid_finish_Message` | `<QIHI` | 18 |  |
| `0x0c11` | `FG2C_party_dungeon_round_state_Message` | `<IHIIII` | 22 |  |
| `0x0c14` | `FG2C_party_dungeon_result_Message` | `<IBQ` | 13 | `<QBIHQ` (23 B) |
| `0x0c16` | `FG2C_party_dungeon_2_result_Message` | `<BIIIQ` | 21 |  |

### 1702 schedule

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `—` | `FL2C_ans_mapcontent_schedule_Message` | `<IIB` | 9 | `<BBBBBHBBBBIIIIHBBBQQ` (48 B) |
| `0x0534` | `FL2C_restore_schedule_list_Message` | `<II` | 8 | `<IBQQBBI` (27 B) |
| `—` | `FL2C_ans_minewar_skirmish_schedule_Message` | `<IQIIQB` | 29 |  |

### 1802/1803 dungeon grade

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `—` | `FL2C_ans_max_cleared_dungeon_grade_Message` | `<IIQIQIf` | 36 |  |
| `—` | `FC2L_ask_max_cleared_dungeon_grade_Message` | _(corpo vazio / ask sem payload)_ | — | — |

### 1805/1806 boss schedule

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `—` | `FL2C_ans_boss_schedule_Message` | `<BBII` | 10 | `<QIIBQQIBBBI` (44 B) |
| `—` | `FC2L_ask_boss_schedule_Message` | _(corpo vazio / ask sem payload)_ | — | — |

### 1809/180a population

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `—` | `FL2C_ans_map_content_user_count_Message` | `<HBB` | 4 | `<QIIIIIIII` (40 B) |
| `—` | `FC2L_ask_map_content_user_count_Message` | _(corpo vazio / ask sem payload)_ | — | — |

### 1814 mothership

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `0x1816` | `FL2C_ans_event_mother_ship_status_list_Message` | `<BBII` | 10 | `<IIIIIQQBB` (38 B) |
| `0x1814` | `FL2C_noti_event_mother_ship_schedule_Message` | `<BBIQ` | 14 |  |
| `0x1815` | `FC2L_ask_event_mother_ship_status_list_Message` | _(corpo vazio / ask sem payload)_ | — | — |

### 2301/2302 map exploration

| Opcode | Classe | Formato | Bytes | Registro de lista |
| --- | --- | --- | ---: | --- |
| `0x2602` | `FL2C_ans_exploration_report_info_Message` | `<HII` | 10 |  |
| `0x2302` | `FL2C_exploration_map_activate_Message` | `<HIIIIQ` | 26 |  |
| `—` | `FL2C_exploration_schedule_info_Message` | `<IIQ` | 16 |  |
| `0x2301` | `FL2C_exploration_map_complete_info_Message` | `<BII` | 9 | `<IBBBBBBBBBBBBBBBB` (20 B) |

## Confiança

- **Alta:** opcode (imediato do getter) e larguras de campo do (de)serializador — método validado contra 3 mensagens conhecidas.
- **Média:** semântica dos campos (nomes) — inferida por analogia às mensagens confirmadas; os nomes exatos por campo dependem do getter de log, que só expõe subconjuntos.
- **Pendente (dinâmico):** valores em si (HP, contribuição, agenda ativa) continuam sendo estado de servidor; este relatório entrega apenas a **estrutura** para decodificar quando houver captura.

## Observações

- `no serializer`/`ask sem payload`: mensagens cliente→servidor `FC2L_ask_*` normalmente têm corpo vazio ou trivial; não foram forçadas.
- Alguns opcodes vieram fora da faixa palpitada no doc (ex.: `guild_raid_finish`=`0x0d6b`, `exploration_report_info`=`0x2602`): o valor aqui é o **imediato real** lido do binário e deve prevalecer sobre o palpite por propósito.
- Campos `B` isolados entre `Q` (ex.: `worldboss_hp_sync` `<IQQBQB>`) são flags/estado; a máscara exata segue por confirmar em captura.

## Artefatos

- `job1_all_opcodes.csv` — 1.771 classes × opcode (1.466 resolvidos) e direção.
- `job1_pending_layouts.json` — layouts estruturados das classes pendentes (campos, offsets, tipos).
- `all_message_classes.txt` / `all_fields.json` — catálogo bruto.

## Próximo passo

Com estes formatos, `rfnext_frame_decode.py` pode ganhar decoders para os opcodes de boss/world-boss/
quest/dungeon/mothership/exploração. Quando o servidor voltar, uma captura curta confirma semântica e
sinalização campo-a-campo, promovendo a confiança de média→alta.