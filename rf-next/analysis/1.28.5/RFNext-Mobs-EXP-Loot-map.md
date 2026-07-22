# Mobs, EXP e loot — RF ONLINE NEXT 1.28.5

## Estado atual

As camadas `patch1 > patch0 > base` contêm 10.819 registros em `RF_NPCTable`.
Destes, 2.783 apontam para um `RewardIndex`, 2.566 têm uma relação estrutural
com EXP e todos os valores abaixo são do cliente Android 1.28.5.

| Área | Estado | Evidência |
|---|---|---|
| identidade e nível | confirmado | `NPCIndex`, nome PT-BR, nível, tipo, subtipo e grade |
| spawn | confirmado | 7.681 entradas, 4.813 NPCs, 238 mapas e 774 pares mapa/região |
| EXP base candidata | confirmado estruturalmente | 2.566 NPCs ligados ao item interno `900` (`EXP`) |
| loot possível | confirmado estruturalmente | 169.122 relações entre 2.783 NPCs e 1.328 itens |
| quantidade mínima | confirmado | `MinValue` em `RF_SubGroupInfo.sqlite` |
| chance de drop | não confirmada | os bancos não possuem coluna de probabilidade |
| HP final por NPC | disponível na rede | `FG2C_appear_monster_list_Message` contém `m_MaxHP` e `m_CurrentHP` |
| ataque/defesa finais | potencial na rede | `FG2C_ans_unit_stat` leva `UID` e o bloco completo de atributos; falta provar que o servidor o envia para mobs |

## Catálogo de mobs

`RF_NPCTable` fornece:

- `NPCIndex`, nível, `RewardIndex`, aparência, AI e opções;
- nome e título;
- tipo, subtipo, grade e tendência de ataque;
- habilidade básica e habilidades controladas pela AI;
- raio, altura, distância de alerta, mapa e região de spawn.

`RF_MapInfoTable_Spawn` acrescenta posição, direção, quantidade colocada e
distância de combate. A soma bruta de `SpawnValue` é 254.670. A tabela específica
de chefes contém 78 entradas, 69 NPCs distintos e 33 mapas; `RF_BossReward`
possui 79 NPCs com configuração de recompensa.

Para os alvos das capturas, a localização estática ficou definida assim:

| NPC | Área PT-BR | Mapas | `SpawnValue` | `DefaultBattleRange` |
| --- | --- | --- | ---: | ---: |
| Ramon Clops Sniper | Deserto de Ramon | 101 | 33 | 200 |
| Junker Desenfreado | Deserto de Ramon | 101 | 36 | 200 |
| Fundidor Buscador | Campo de Mineração Público 2º Andar | 612/615/618/624 | 20 por mapa | 200 |
| Fantasma do Pesadelo | Campo de Mineração Público 2º Andar | 612/615/618/624 | 40 por mapa | 200 |
| Fundidor Guardião | Campo de Mineração Público 2º Andar | 612/615/618/624 | 20 por mapa | 200 |
| Fundidor Purificador | Campo de Mineração Público 2º Andar | 612/615/618/624 | 20 por mapa | 200 |

`SpawnValue` é configuração estática, não contagem viva garantida. Os quatro
índices do Campo de Mineração reutilizam a mesma geometria e as mesmas três
posições configuradas por NPC, provavelmente instâncias/camadas do mesmo mapa.

## EXP

A ligação encontrada é:

```text
RF_NPCTable.RewardIndex
  -> RF_RewardTableRow.RewardIndex
  -> RF_RewardTableRow.SubGroupIndex
  -> RF_SubGroupInfoRow.SubGroupIndex
  -> RewardItemIndex 900 (EXP), MinValue
```

Há 2.566 NPCs nessa cadeia, com 160 valores distintos entre 10 e 30.459.500.
`MinValue` é uma base forte, mas não necessariamente o ganho exibido: bônus de
nível, conta, servidor, coleção, evento ou grupo podem alterar o resultado.

O ELF também confirma `FL2C_update_exp_Message`, com os campos `m_ActionCode`,
`m_HighestLevel`, `m_BeforeLevel`, `m_Level`, `m_Exp` e `m_GainExp`. Essa mensagem
é o melhor ponto para medir o ganho real por abate em uma captura controlada.
O serializador em `0x06131170` grava um corpo fixo de 24 bytes little-endian:
quatro inteiros de 16 bits seguidos por dois inteiros de 64 bits. Em Python, o
formato é `<HHHHqq`, na mesma ordem dos campos acima.

## Loot e droptable

Os bancos SQLite expõem somente:

- `RF_RewardTableRow`: `RewardIndex`, `BoxType`, `SubGroupIndex`;
- `RF_SubGroupInfoRow`: `SubGroupIndex`, item, quantidade mínima, encantamento
  e tipo de biosuit.

As 169.122 relações geradas têm 169.074 nomes de item resolvidos em PT-BR. A
repetição de um subgrupo ocorre no máximo duas vezes, mas isso não prova peso ou
probabilidade. Portanto o conjunto atual é uma lista de drops possíveis, não uma
droptable com percentuais confirmados.

Há uma confirmação adicional no código nativo: as funções em `0x06784d54` e
`0x06784f08` montam, respectivamente, as consultas `WHERE RewardIndex = {0}` e
`WHERE SubGroupIndex = {0}`. O chamador percorre todas as linhas retornadas por
`RewardIndex`, consulta cada subgrupo e copia todas as linhas de item para uma
lista usada pela interface de recompensa. Não há sorteio, comparação de peso ou
percentual nesse caminho. Além disso, as 49.988 linhas de recompensa alcançadas
pelos 2.783 NPCs usam `ITEM_REWARD_BOX_TYPE_NONE`.

Isso fortalece a leitura do banco como catálogo de candidatos. A seleção do que
é realmente concedido provavelmente ocorre no servidor; o cliente permite listar
possibilidades, mas não demonstra chances nem se todos os subgrupos são entregues.

Entre os candidatos estáticos de skill desses NPCs aparecem: Otimização e
Adaptação à Dor para Ramon; Habilidades de Combate V e Constante II para Junker;
Habilidades de Combate IV e Otimização para Buscador; Habilidades de Combate V e
Constante II para Fantasma; Reforço de Bloqueio e Adaptação à Dor para Guardião;
Otimização e Mente Clara para Purificador. Isso confirma apenas presença no
grupo de recompensa, não chance nem drop observado.

Na rede, mudanças de inventário aparecem por mensagens como
`FL2C_stackable_item_update_Message`, `FL2C_equip_item_update_Message` e
`FL2C_currency_update_Message`. A associação entre uma morte e esses eventos
precisa ser validada por ordem temporal numa captura curta e rotulada.

## Status dos mobs na rede

`FG2C_appear_monster_list_Message` possui uma função de identificação que retorna
`0x0307`. Como essa função também aparece em outras classes, esse valor não deve
ser tratado ainda como opcode exclusivo da mensagem. Cada unidade expõe:

```text
m_UID, m_SummonerUID, m_SummonerPCID, m_NpcIndex,
m_MaxHP, m_CurrentHP, m_Position, m_Direction, m_Speed,
m_Realm, m_PatrolOffset, m_Flag, m_AttackSpeedRate,
m_ActionSpeedRate, m_GuildID
```

O serializador em `0x06017fe8` confirma que o corpo começa com a quantidade de
unidades em 16 bits e contém registros fixos de 83 bytes. O formato little-endian
de cada registro é `<IIQIQQfffBfBfffBIIQ`; os vetores `Position` e
`PatrolOffset` ocupam três `float32` cada. Assim, o tamanho esperado do corpo é
`2 + quantidade * 83` bytes.

Isso permite relacionar `NPCIndex` ao catálogo e obter HP real da instância sem
OCR. As capturas abaixo confirmaram o enquadramento, a identificação externa da
mensagem e a remontagem entre segmentos TCP.

O enum refletido `eFIELD_MONSTER_FLAG` também permite interpretar `m_Flag` como
uma máscara de bits: 0 `ACTIVATING`, 1 `ACTIVATE`, 2 `REGEN`, 3 `COMBAT`, 4
`ALIVE` e 5 `SKILL_EFFECT`. Nos cinco NPCs com amostra acumulada, todas as
aparições tinham `Realm=13`, confirmado no enum `eREALM` como `REALM_MONSTER`,
velocidade 150 e taxas brutas de ataque/ação 10.000. As máscaras observadas
foram 22 (`ACTIVATE|REGEN|ALIVE`) e, em parte dos Ramons e Purificadores, 18
(`ACTIVATE|ALIVE`). O decodificador agora emite também `realm_name` e
`flag_names`.

| NPC | Aparições | HP sempre igual | `Flag 22` | `Flag 18` |
| --- | ---: | ---: | ---: | ---: |
| Ramon Clops Sniper | 112 | 32.560 | 96 | 16 |
| Junker Desenfreado | 22 | 30.540 | 22 | 0 |
| Fantasma do Pesadelo | 77 | 22.648 | 77 | 0 |
| Fundidor Guardião | 184 | 29.037 | 184 | 0 |
| Fundidor Purificador | 222 | 25.407 | 167 | 55 |

Para acompanhar dano e morte, `FG2C_do_damage_Message` pertence ao grupo
`id_Skill`, retorna o identificador de submensagem `0x061A` e serializa 17 bytes:
`m_UID` (`uint32`), `m_Damage` (`int32`), `m_CurrentHP` (`int64`) e `m_UnitState`
(`uint8`). O formato Python é `<IiqB`. A enumeração de estado também foi
recuperada do ELF:

```text
0 INACTIVE, 1 ALIVE, 2 DYING, 3 DEAD, 4 GHOST
```

Logo, `UID` liga a aparição ao dano, e `CurrentHP == 0` junto de `UnitState == 3`
é o marcador mais forte para correlacionar o abate. A mensagem complementar
`FG2C_damage_log_Message` usa o subidentificador `0x061C` e acrescenta
`CasterUID`, `TargetUID`, `SkillIndex`, `SkillEffectIndex`, `Damage` e um log.

Também foi localizada `FG2C_ans_unit_stat_Message` no grupo `id_Player`, com
subidentificador `0x0422`. Ela contém `m_Ret` (`uint16`), `m_UID` (`uint32`) e um
bloco fixo `m_Stat` de 752 bytes, totalizando 758 bytes de corpo. Esse bloco tem
187 valores e inclui `STR`, `DEX`, `VIT`, `INT`, `WIS`, `AGI`, `P_AtkPow`,
`P_DefPow`, `F_AtkPow`, `F_DefPow`, `AtkPow`, `DefPow`, `MaxHP`, `HitPow`,
`DodgePow`, `CriHitPow`, `CriResPow` e diversas taxas derivadas.

Esse é um caminho plausível para ataque e defesa finais, mas ainda não é uma
confirmação por mob: a mensagem pertence ao grupo `Player` e não há evidência nas
capturas atuais de que ela seja enviada com o `UID` de um NPC. A mensagem de jogo
`FG2C_unit_stat_changed` (`0x0324`) atualiza apenas `UID`, velocidade e taxas de
ataque/ação.

## Captura real de combate

A captura `rfnext-pc-20260721-191807.pcap` observou simultaneamente dois clientes
por 59,31 segundos: 12 mil pacotes, 7.047.082 bytes e SHA-256
`be5d61f6517b86d2d5a5b7b43473c1bf14353a46af9e88c4513ab3a19c89b4f2`.
O pacote externo `FG2C_bundle_message` (`0x010A`) continha 5.397 mensagens de
jogo internas, incluindo 162 listas de aparição e 147 eventos
`FG2C_dying_unit`. Este último fornece `UID`, `KillerUID` e motivo da morte.

### Cliente nas portas locais 43711/43703

- 23 concessões de recompensa e 23 atualizações de EXP;
- EXP estática 9.669; EXP observada 14.986 por evento, igual a
  `floor(9.669 * 1,55)`;
- 483 créditos por evento contra base estática 454;
- 2.810 de Contribuição Comum, igual à base estática;
- `KillerUID 268525255` aparece em 23 mortes: 13 Fundidores Guardiões, três
  Fantasmas do Pesadelo e sete UIDs que já existiam antes do início da captura;
- drops adicionais observados: Filamento Inferior 2/23, Gás Sagrado x10 2/23,
  Pistola de Combate Eminence 1/23 e Abrasivo Inferior 1/23.

Os mobs de nível 70 observados compartilham a base de EXP 9.669, crédito 454 e
contribuição 2.810. Todos os itens recebidos constam nas listas candidatas deles.

### Cliente nas portas locais 43710/43702

- 19 concessões de recompensa e 19 atualizações de EXP;
- EXP estática 10.869; ganho normal 16.303, igual a
  `floor(10.869 * 1,50)`;
- um evento com `ActionCode 1006` concedeu 163.030 EXP, exatamente dez vezes o
  ganho normal;
- 511 créditos por evento contra base estática 474;
- 4.610 de Contribuição Comum, igual à base estática;
- Ramon Clops Sniper e Junker Desenfreado, ambos de nível 75, foram os mobs
  identificados nesse fluxo;
- drops adicionais observados: Kit de Upgrade de Acessório 1/19 e Placa de
  Metal Fragmentada 1/19.

Essas frações são frequências desta amostra curta, não probabilidades oficiais.
Elas confirmam que `FL2C_drop_item_field` é a resposta de recompensa por abate:
cada entrada traz item, quantidade, total acumulado e `ActionCode`.

## Captura ampliada e correlação por tempo

A segunda captura, `rfnext-pc-20260721-193015.pcap`, observou os dois clientes
por 298,50 segundos: 71.394 pacotes, 38.239.368 bytes e SHA-256
`4c847c8172b5772a6954554e9b3552df54d1bed7d74b3fc7806b884a4a8ba338`.
Foram extraídas mais 219 recompensas: 117 no cliente das portas 43711/43703 e
102 no cliente 43710/43702.

O decodificador agora preserva o timestamp do pacote que completou cada frame
TCP e o propaga às mensagens internas de `FG2C_bundle_message`. Nas duas
capturas, os 261 eventos de recompensa puderam ser pareados um a um com mortes:

- todas as recompensas chegaram depois da respectiva morte;
- o intervalo morte-recompensa ficou entre 53 e 488 ms;
- não houve pares invertidos nem intervalo superior a dois segundos;
- no cliente 43711/43703, as 140 recompensas coincidiram com as 140 mortes pelo
  `KillerUID 268525255`;
- no cliente 43710/43702, as 121 recompensas coincidiram com todas as 121 mortes
  de `KillerUID` não zero, inclusive UIDs diferentes do personagem observado.

O último caso demonstra compartilhamento de recompensa naquele fluxo, embora a
captura sozinha não diferencie grupo, pet, invocação ou outra regra do servidor.

### Amostra acumulada atribuída por NPC

| NPC | HP observado | Abates identificados | EXP normal | Crédito | Contribuição |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fundidor Guardião da Pedra Sagrada (`361270`) | 29.037 | 104 | 14.986 | 483 | 2.810 |
| Fantasma do Pesadelo (`361269`) | 22.648 | 21 | 14.986 | 483 | 2.810 |
| Fundidor Purificador da Pedra Sagrada (`361271`) | 25.407 | 3 | 14.986 em 2/3 | 483 em 2/3 | 2.810 em 2/3 |
| Ramon Clops Sniper (`305208`) | 32.560 | 88 | 16.303 | 511 | 4.610 |
| Junker Desenfreado (`305215`) | 30.540 | 22 | 16.303 | 511 | 4.610 |

Um dos três Purificadores concedeu 6.953 EXP, 223 créditos e 1.303 de
contribuição. Como os demais valores foram normais e a tabela estática é igual à
dos outros mobs de nível 70, o evento é mantido como recompensa reduzida sem
atribuir uma fórmula. Nesse abate, porém, outro jogador (`268436408`) causou um
impacto de 5.571, além de dois impactos do jogador local. As três parcelas
recebidas ficaram entre 46,17% e 46,40% do normal; os dois Purificadores atacados
somente pelo jogador local deram recompensa integral. Isso sustenta divisão por
participação, sem demonstrar ainda o cálculo do servidor. Outros 23 abates não puderam receber
`NPCIndex` porque seus UIDs já estavam ativos antes do início das capturas.

Frequências empíricas dos drops adicionais, excluindo EXP, crédito e
contribuição:

| NPC | Item | Observado |
| --- | --- | ---: |
| Fundidor Guardião | Gás Sagrado x10 | 7/104 (6,73%) |
| Fundidor Guardião | Placa de Metal Fragmentada (`275000`) | 2/104 (1,92%) |
| Fundidor Guardião | Filamento Inferior (`270003`) | 2/104 (1,92%) |
| Fundidor Guardião | Pistola de Combate Eminence (`1002415`) | 1/104 (0,96%) |
| Fundidor Guardião | Abrasivo Inferior (`275001`) | 1/104 (0,96%) |
| Fundidor Guardião | Matriz de Cristal (`153050`) | 1/104 (0,96%) |
| Fundidor Guardião | Filamento Inferior (`275003`) | 1/104 (0,96%) |
| Fundidor Guardião | Kit de Upgrade de Acessório (`5202`) | 1/104 (0,96%) |
| Fantasma do Pesadelo | Gás Sagrado x10 | 2/21 (9,52%) |
| Fantasma do Pesadelo | Abrasivo Inferior (`275001`) | 2/21 (9,52%) |
| Fantasma do Pesadelo | Feixe de Fibra Inferior (`275002`) | 1/21 (4,76%) |
| Ramon Clops Sniper | Feixe de Fibra Inferior (`275002`) | 3/88 (3,41%) |
| Ramon Clops Sniper | Placa de Metal Fragmentada (`275000`) | 1/88 (1,14%) |
| Ramon Clops Sniper | Feixe de Fibra Inferior (`270002`) | 1/88 (1,14%) |
| Junker Desenfreado | Placa de Metal Fragmentada (`270000`) | 1/22 (4,55%) |

Todos os 15 pares NPC-item acima existem no catálogo estático de candidatos.
Esses percentuais são somente frequências desta amostra e ainda têm grande
incerteza, principalmente nas linhas com 21 ou 22 abates.

Entre as 261 recompensas, 231 não trouxeram item opcional, 29 trouxeram um e uma
trouxe dois. O caso duplo foi um Fundidor Guardião com Filamento Inferior
`270003` e Gás Sagrado x10; portanto, não há limite rígido de um drop opcional
por abate. `drop_item_field` e `update_exp` parearam 261/261 no mesmo timestamp,
sem divergência de EXP ou `ActionCode`. O intervalo morte-recompensa teve
mediana 290,063 ms e P95 439,468 ms.

### Significado dos ActionCodes

A tabela refletida de `eACTION_CODE` no ELF, iniciada nesse trecho em
`0x097bd500`, fornece diretamente os valores:

```text
960  ACTION_CODE_KILLED_NPC
1000 ACTION_CODE_FIELDDROP
1001 ACTION_CODE_MODE_REWARD
1002 ACTION_CODE_FIRST_HIT_REWARD
1003 ACTION_CODE_LAST_HIT_REWARD
1004 ACTION_CODE_FIELDDROP_TEST
1005 ACTION_CODE_EXP_BY_FINISH_SKILL
1006 ACTION_CODE_EXP_BY_FINISH_ONEKILL
```

Assim, os cinco eventos `1006` das duas capturas não são corrupção do protocolo:
o servidor os marcou como `EXP_BY_FINISH_ONEKILL` e concedeu exatamente dez vezes
o EXP normal. O jogador confirmou que esse código representa finalizadores que
concedem bônus de EXP; o multiplicador 10× está demonstrado nestas capturas, sem
ser generalizado ainda para toda modalidade ou evento do jogo.

A correlação golpe final-recompensa fechou os cinco casos: três terminaram com a
skill `1070122` (Lâmina de Força Deadly) e dois com `1080122` (Arma Mortal
Blaster). Nenhum abate normal `1001` terminou nessas skills na amostra. O bônus
`1006` alterou somente a EXP; crédito e contribuição continuaram normais com
`ActionCode 1001`.

Os 15 abates do fluxo 43710 cujo `KillerUID` não era o personagem foram causados
por 12 instâncias do mesmo `NPCIndex 589`: 11 Ramon e quatro Junker, todos com
EXP integral. A tabela descreve o 589 como entidade nível 5, tipo 2/subtipo 125,
skill básica `1070133` e nome vazio. Isso é evidência forte de companheiro ou
invocação do jogador, mas não identifica ainda o rótulo exato da entidade.

## Dano e resistência efetiva

O dano não apareceu nas mensagens isoladas `FG2C_do_damage`/`damage_log`, mas foi
recuperado nas respostas de skill. `FG2C_ans_use_skill` (`0x0602`) possui 74 bytes
fixos e zero ou mais resultados de 66 bytes. Cada resultado contém:

```text
UID, ProjectileTargetPos, TargetPos, OptionFlag,
ShieldDamage, HPDamage, FinalHP,
ProjectileActivateTime, ProjectileDestTime, Flag, StiffEndTick
```

`FG2C_ans_use_normal_skill` (`0x060D`) possui 42 bytes fixos e resultados de 46
bytes com o subconjunto `UID`, `TargetPos`, `OptionFlag`, `ShieldDamage`,
`HPDamage`, `FinalHP`, `Flag` e `StiffEndTick`. Os tamanhos observados na rede
seguem exatamente essas fórmulas.

Na captura ampliada foram decodificados 2.300 impactos contra NPCs identificados.
Não houve `ShieldDamage` diferente de zero nesses impactos. O `HPDamage` não é
limitado pelo HP restante: golpes finais podem exceder o HP máximo, enquanto
`FinalHP` fica em zero.

| NPC | Impactos visíveis | Dano mediano | P95 | Máximo |
| --- | ---: | ---: | ---: | ---: |
| Ramon Clops Sniper | 268 | 6.783 | 19.685 | 42.007 |
| Junker Desenfreado | 68 | 5.840 | 21.263 | 30.421 |
| Fundidor Guardião | 813 | 4.458 | 20.843 | 38.866 |
| Fundidor Purificador | 627 | 4.538 | 18.936 | 41.198 |
| Fundidor Buscador | 267 | 6.847 | 24.104 | 61.599 |
| Fantasma do Pesadelo | 257 | 4.386 | 18.401 | 77.562 |

Essa tabela mistura skills, jogadores e acertos elevados; ela descreve o combate
observado, não um atributo bruto de defesa. Um controle melhor é comparar o mesmo
personagem, a mesma skill e `OptionFlag 0`. Para o personagem `276859829`, as
quatro skills normais `1070001` a `1070004` causaram no Junker aproximadamente
84% a 86% do dano mediano causado no Ramon. Isso é evidência de que o Junker teve
mitigação efetiva maior nessa situação, mas ainda não fornece o valor interno de
`DefPow`.

Para o personagem `268525255`, a skill normal `1080001` com `OptionFlag 0` teve
mediana 4.523 no Fundidor Guardião (184 impactos), 4.684 no Fantasma (33) e 5.355
no Purificador (sete). A amostra do Purificador ainda é pequena. `OptionFlag 1`
forma repetidamente um grupo de dano cerca de 1,5× a 1,6× maior; o comportamento
é compatível com acerto crítico, mas o nome desse bit ainda não foi confirmado no
enum e por isso permanece sem rótulo definitivo.

Uma separação mais completa de `1080001` contra o Guardião obteve medianas 4.468
para `OptionFlag 0`, 7.383 para 1, 6.009 para 32 e 10.494 para 33. O mesmo padrão
se repete no Fantasma. Como 33 combina os bits 0 e 5 e os multiplicadores se
acumulam, eles parecem modificadores independentes; somente o bit 0 permanece
compatível com crítico, sem nome confirmado.

O campo `Flag` do resultado de efeito separou letalidade perfeitamente nesta
amostra: flags 0/1 tiveram `FinalHP > 0` em 2.178/2.178 casos, enquanto 2/3
tiveram `FinalHP == 0` em 587/587. A flag 2 apareceu apenas em 22 golpes de
skills especiais cujo dano era pelo menos o HP máximo; a flag 3 cobriu os demais
golpes letais. A sequência aritmética de HP fechou exatamente em 2.634/2.765
impactos (95,26%); os 131 desvios impedem tratar toda sequência ou TTK como
telemetria completa.

### Mecânica estática das skills dos mobs

As skills abaixo vêm diretamente de `BasicSkillIndex`. Todos os seis NPCs usam a
linha de AI 1, cujas listas de skills condicionais/especiais estão vazias. Cada
skill abaixo tem um alvo máximo, contra-ataque permitido, dano fixo adicional
zero e absorção zero. Os tempos aparentam milissegundos e `Rate=10000`
provavelmente representa 100%, mas essas duas interpretações ainda são
inferências; os valores brutos são os da tabela.

| NPC/skill | Tag | Normal | Tipo dano | Rate | CD | Precast | Próxima skill | Alcance |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fantasma `7008401` | `Ghost.Combo01` | 0 | 2 | 10.000 | 1.000 | 600 | 1.000 | 150 |
| Purificador `7013801` | `HolystoneSweeper.Combo01` | 1 | 1 | 10.000 | 1.000 | 500 | 1.330 | 700 |
| Buscador `7014201` | `HolystoneStalker.Combo01` | 1 | 1 | 10.000 | 1.000 | 400 | 1.670 | 100 |
| Buscador `7014202` | `HolystoneStalker.Combo02` | 1 | 1 | 10.000 | 1.000 | 600 | 1.830 | 100 |
| Buscador `7014203` | `HolystoneStalker.Active01` | 0 | 1 | 10.000 | 10.000 | 800 | 2.000 | 700 |
| Guardião `7014401` | `HolystoneGuardian.Combo01` | 1 | 1 | 10.000 | 1.000 | 1.000 | 2.480 | 200 |
| Guardião `7014402` | `HolystoneGuardian.Combo02` | 1 | 1 | 10.000 | 1.000 | 800 | 2.520 | 200 |
| Guardião `7014403` | `HolystoneGuardian.Combo03` | 1 | 1 | 10.000 | 1.000 | 700 | 1.850 | 200 |
| Ramon `7015001` | `ClopsDeceiver.Combo01` | 1 | 1 | 10.000 | 1.000 | 700 | 1.330 | 700 |
| Junker `7015801` | `JunkWalker.Combo01` | 1 | 1 | 10.000 | 1.000 | 900 | 1.670 | 150 |
| Junker `7015802` | `JunkWalker.Combo02` | 1 | 1 | 10.000 | 1.000 | 900 | 1.670 | 150 |

O campo `AttackType` do NPC deve continuar numérico: a tabela o descreve apenas
como tendência de ataque e não fornece enum para chamá-lo de físico/Force ou
corpo a corpo/distância. A tabela `RF_NPCStat` possui o esquema de 45
multiplicadores de HP, ataque, defesa, acerto e resistências para normal/elite/
boss, mas declara zero linhas nesta versão. Portanto, não existe base legítima
offline para preencher ataque ou defesa finais numéricos.

#### Validação temporal pela rede

Uma mesma execução de skill aparece com o mesmo `UseSkillUniqID` primeiro como
`ResponseNumber 0` e depois como `ResponseNumber 1`. O intervalo entre as duas
respostas acompanha `Precast_Time` com pequeno atraso de rede/processamento,
confirmando que a unidade da tabela é milissegundo.

| Skill | Pares | `Precast_Time` | Mediana observada |
| --- | ---: | ---: | ---: |
| Fantasma `7008401` | 127 | 600 ms | 644,5 ms |
| Purificador `7013801` | 166 | 500 ms | 538,5 ms |
| Buscador `7014201` | 18 | 400 ms | 457,7 ms |
| Buscador `7014202` | 14 | 600 ms | 634,9 ms |
| Buscador `7014203` | 63 | 800 ms | 831,9 ms |
| Guardião `7014401` | 44 | 1.000 ms | 1.014,0 ms |
| Guardião `7014402` | 44 | 800 ms | 843,9 ms |
| Guardião `7014403` | 49 | 700 ms | 758,5 ms |
| Ramon `7015001` | 87 | 700 ms | 754,3 ms |
| Junker `7015801` | 18 | 900 ms | 911,0 ms |
| Junker `7015802` | 16 | 900 ms | 946,8 ms |

Medindo somente inícios de execuções distintas do mesmo UID, os ciclos medianos
entre ataques foram 2,395 s para Ramon (18 intervalos), 2,126 s para Junker
(15), 1,854 s para Buscador (8), 2,026 s para Fantasma (69), 2,710 s para
Guardião (32) e 2,402 s para Purificador (48). São cadências do combate e das
condições observadas, não garantias universais: troca de skill, alvo, animação e
estado do NPC podem alterar o ciclo.

Não foi possível extrair respawn normal de forma segura. As mensagens de
aparição marcam entrada no campo de visão e não necessariamente nascimento no
ponto de spawn; as tabelas comuns de spawn não possuem temporizador de respawn.
Somente `RF_RandomBossSpawn` declara limites explícitos, destinados a chefes
aleatórios. Por isso não foi atribuída uma duração de respawn aos mobs comuns.

### Dano dos mobs contra os personagens observados

| NPC atacante | Impactos no personagem | Dano mediano | Faixa observada |
| --- | ---: | ---: | ---: |
| Ramon Clops Sniper | 68 | 243 | 0–384 |
| Junker Desenfreado | 25 | 282 | 0–396 |
| Fundidor Guardião | 40 | 257 | 152–301 |
| Fantasma do Pesadelo | 24 | 212 | 0–317 |
| Fundidor Purificador | 1 | 217 | 217 |

Esses números já separam as skills dos NPCs (`7015001` para Ramon; `7015801` e
`7015802` para Junker; `7014401`–`7014403` para Guardião; `7008401` para
Fantasma; `7013801` para Purificador). Contudo, o dano recebido depende da defesa,
reduções, buffs e estados de cada personagem; não deve ser publicado como ataque
bruto universal do mob.

O tempo entre o primeiro impacto decodificado e a morte também pôde ser medido.
As medianas do combate visível foram 1,76 s para Ramon, 1,74 s para Junker, 2,34 s
para Guardião, 1,98 s para Purificador, 1,53 s para Buscador e 1,53 s para
Fantasma. Isso é TTK das builds e grupos presentes na captura, não uma propriedade
fixa dos NPCs.

## Próxima validação útil

O protocolo e a correlação temporal estão confirmados. Enquanto o servidor está
em manutenção, a análise offline já esgotou a tabela `RF_NPCStat` e avançou até
os limites verificáveis de skills e flags. Quando o jogo voltar, o próximo passo
útil é manter capturas longas e acumular centenas ou milhares de mortes por
`NPCIndex`, além de registrar build/party para testar participação. Os resultados
atuais já separam os mobs, mas 104 e 88 mortes ainda são pouco para itens raros;
21 e 22 são apenas sinais iniciais.
