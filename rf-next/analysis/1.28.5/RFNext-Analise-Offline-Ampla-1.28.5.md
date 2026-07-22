# Análise offline ampla — RF ONLINE NEXT 1.28.5

## Escopo e confiança

Esta análise usa somente o cliente Android 1.28.5 já extraído, o
`rfnext-data.sqlite`, as tabelas RFTable/SQLite e o `libUnreal.so`. Não depende
de nova captura, Ghidra ou controle de tela.

Três níveis de evidência devem permanecer separados:

- **estático confirmado:** definição presente no cliente e relações fechadas;
- **baseline estática:** taxa ou agenda presente no cliente, mas potencialmente
  substituível pelo servidor;
- **dinâmico pendente:** preço, ativação, população, dano final ou probabilidade
  que somente o servidor determina.

## Integridade e cobertura do banco

- 509 RFTable importadas: 1.612.677 linhas declaradas e importadas;
- dois SQLite importados: 119.173 linhas;
- total das fontes: 1.731.850 linhas;
- 511 verificações de contagem passaram;
- 402 verificações de chave primária passaram;
- nenhuma relação órfã nas cadeias de recompensa, exceto o item interno de EXP
  `900`, tratado intencionalmente como entidade especial.

Cinco tabelas são legitimamente vazias: `RF_AutoQuestPlay`,
`RF_CollectionTable`, `RF_NPCStat`, `RF_StatChangeMatchContents` e
`RF_WeaponModelTable_Enchant`. `RF_RewardTable.RFTable` e
`RF_SubGroupInfo.RFTable` são marcadores; os dados reais estão nos SQLite
correspondentes e foram importados.

Cobertura de nomes PT-BR:

| Entidade | Cobertura não vazia |
| --- | ---: |
| Itens | 99,25% |
| Skills | 97,10% |
| NPCs | 86,03% |
| Biosuits/status usados nas análises de classe | 100% |

## Inventário dos sistemas

| Domínio | Conteúdo estático principal |
| --- | --- |
| progressão | 200 níveis, 187 status, 5.215 skills, 2.549 buffs de skill |
| classes | 243 biosuits, 192 skills principais de classe |
| itens | 8.231 itens, 1.216 curvas de aprimoramento, 1.358 opções |
| crafting | 1.086 receitas, 15 tiers de alquimia, 20 categorias Prime |
| mundo | 508 mapas, 791 regiões, 7.681 configurações de spawn |
| NPCs | 10.819 NPCs e 4.813 `NPCIndex` distintos em spawns |
| quests | 1.796 quests, 6.822 alvos e 1.797 tabelas de recompensa |
| missões | 14.580 registros de missão |
| coleções | 4.503 coleções de item e 4.383 recompensas parciais |
| conquistas | 222 grupos e 1.637 níveis de conquista |
| conteúdo | world boss, time dungeon, party dungeon, guild raid, Babylon, guerras |

## Progressão de personagem

`RF_LevelUpTable` cobre os níveis 1–200. `PC_NeedExp` é monotônico e possui um
valor distinto em cada nível.

| Faixa | Soma tabular de EXP necessária |
| --- | ---: |
| níveis 2–100 | 8.860.877.171.309 |
| níveis 2–200 | 3.022.660.132.182.889 |

`PC_GetStatPoint` e `PC_TotalStatPoint` são zero em todos os níveis; o cliente
não modela pontos primários distribuíveis nessa curva. Os aumentos tabulares
acumulados até 200 são: ataque 540, defesa 560, HP 52.999, FP 2.665, precisão
572, evasão 858, crítico 563 e resistência crítica 666.

### Fórmulas de status confirmadas

Há 25 fórmulas explícitas de atributos e 144 fórmulas de poder de combate. Entre
as relações confirmadas:

```text
HP máximo = VIT × 90 + HP aditivo
FP máximo = WIS × 3 + FP aditivo
Ataque físico parte de FOR
Ataque de Força parte de INT
DEF = DES + DEF aditiva
Evasão = AGI + Evasão aditiva
```

Pesos de poder de combate recuperados:

- ataque, defesa, precisão e evasão: ×8;
- ataque físico e ataque de Força: ×4;
- HP: ×0,2;
- FP: ×0,6.

Isso não fornece a fórmula final de dano contra um alvo. O banco contém
coeficientes e atributos, mas não fecha mitigação, crítico, penetração e demais
modificadores do servidor.

## Classes, biosuits e skills

| Tipo | Família | Fórmula-base |
| ---: | --- | --- |
| 1 | Punisher | física |
| 2 | Phantom | física |
| 3 | Enforcer | Força |
| 4 | Psypher | Força |
| 5 | Dreadnought | física |
| 6 | Technician | Força |
| 7 | Arbiter | Força |
| 8 | Demolition | física |

Classes 1–7 possuem 30 biosuits visíveis cada; Demolition possui 23. O orçamento
total dos seis atributos primários por grau é 30, 54, 96, 180, 318/320 e 528
nos graus 1–6.

Cada classe possui 24 registros principais em `RF_SkillListTable_Biosuit`. A
estrutura identifica nove skills-pai com até três variantes. O fechamento
estático alcançou 408 IDs válidos: 353 aplicam buffs e 256 possuem dano. As 547
referências de buff resolvem sem ausências ou arrays desalinhados.

As primeiras skills-pai abrem explicitamente nos níveis 1, 12 e 24. As seis
seguintes usam `Skill_GetType=2`; o enum não foi nomeado sem uma associação
numérica segura.

### Encantamento de skill

Existem 47 grupos com custos/taxas até +12:

| Nível | Sucesso | Mantém | Rebaixa |
| ---: | ---: | ---: | ---: |
| +1 | 100% | 0% | 0% |
| +2 | 80% | 20% | 0% |
| +3 | 65% | 35% | 0% |
| +4 | 50% | 50% | 0% |
| +5 | 45% | 55% | 0% |
| +6 | 40% | 60% | 0% |
| +7 | 35% | 65% | 0% |
| +8/+9 | 30% | 70% | 0% |
| +10 | 25% | 40% | 35% |
| +11 | 25% | 30% | 45% |
| +12 | 20% | 30% | 50% |

Variantes adicionais abrem em +4, +8 e +12. Há valores preparados até +15,
mas custos, taxas e `SkillMaxEnchantLv` param em +12; +13–15 não devem ser
tratados como acessíveis nesta versão.

Entre as skills de classe, 188 curvas de dano crescem; o aumento mediano do
coeficiente bruto entre nível 0 e +12 é 48,19%. Isso é coeficiente de tabela,
não dano final.

### Encantamento de biosuit

Há sete painéis com sete opções cada; a soma das probabilidades de cada painel é
10.000. A curva comum é 100% nos níveis 1–3, depois 95/90/85/80/75/70/65/60%,
terminando em 55% nos níveis 40–42.

## Itens e equipamentos

`RF_ItemTable` possui 8.231 itens únicos.

| Grau | Itens |
| ---: | ---: |
| 1 | 1.465 |
| 2 | 1.814 |
| 3 | 2.038 |
| 4 | 1.921 |
| 5 | 884 |
| 6 | 109 |

Os tiers vão de 0 a 8. Há 2.008 equipamentos; 1.980 têm progressão de
aprimoramento, 530 têm remodel Prime e 252 apontam diretamente para opções.
`UseLv=0` em todos os equipamentos, portanto esse campo não revela requisito de
nível.

### Aprimoramento de equipamento

- 1.216 combinações únicas de parte, grau e nível;
- níveis 0–15;
- `SuccessRate + Fail_ItemBreakRate = 10.000` em todas as linhas;
- moeda tipo 1, Crédito;
- 23.205 linhas de ganho de status e cobertura integral dos 1.980 equipamentos.

As taxas variam por parte e grau; não existe uma única porcentagem universal por
nível. A faixa de sucesso cai de 100% nos níveis iniciais até 20–25% nos níveis
mais altos, conforme a combinação.

### Opções

- 1.358 opções em 322 grupos;
- 314 grupos ponderados somam 10.000;
- oito grupos especiais/fixos somam zero e não representam roleta;
- os 252 itens ligados diretamente têm `Option_Count_Max=1`.

### Talics

- 576 itens e 18 famílias por combinação disponível;
- todos vinculados e fora do leilão;
- slots por grau 1–6: 0, 1, 2, 2, 3 e 3;
- custo de equipar: 5k, 10k, 30k, 50k, 100k e 200k Créditos.

Conversão lendária:

| Tier | Pedra Prisma | Diamantes |
| ---: | ---: | ---: |
| T1 | 1 | 200 |
| T2 | 2 | 400 |
| T3 | 4 | 800 |

Conversão mítica T1: oito Pedras Prisma e 1.600 Diamantes.

## Crafting, alquimia e remodel

### Craft

- 1.086 receitas, abertura no nível 13;
- as quatro saídas somam exatamente 10.000 em todas as receitas;
- 938 receitas não falham e 148 possuem chance de falha;
- somente 12 definem devolução explícita de material;
- todos os resultados e grupos de materiais não zero resolvem no catálogo.

Perfis mais comuns de `normal/melhor/huge/falha`:

| Perfil | Receitas |
| --- | ---: |
| 100/0/0/0% | 495 |
| 90/10/0/0% | 181 |
| 47/3/0/50% | 136 |
| 90/7/3/0% | 136 |
| 97/0/3/0% | 121 |

### Alquimia

- 15 tiers;
- pontos necessários: 40 até 10.800;
- custo: 100k até 380k Créditos;
- previsão: 50k até 130k;
- as seis taxas somam 10.000 em todos os tiers.

Tier 1 usa 15/10/5/50/15/5%. Tiers 2–15 usam 30/13/2/15/30/10%. Os
90 grupos de recompensa resolvem, mas a probabilidade interna dos itens dentro
de cada grupo não é exposta.

### Remodel Prime

As 20 categorias usam escala 1.000.000: 200.000 de sucesso e 800.000 de falha,
ou 20%/80%. O custo por grau 3–6 é 10k, 20k, 30k e 40k Créditos. Há 530 itens
com entrada e saída Prime válidas.

## Desmontagem

A cadeia correta é:

```text
ItemTable.ItemReward + nível de aprimoramento
  -> ItemTable_Reward.Dismantle_RewardIndex
  -> RewardTableRow.SubGroupIndex
  -> SubGroupInfoRow.RewardItemIndex
```

5.041 itens têm `ItemReward`; todas as 1.919 linhas de recompensa de desmontagem
resolvem. Há 553 itens numa blacklist explícita de venda, descarte, desmontagem
ou troca.

## Leilão, lojas e economia

### Leilão mundial

- 1.688 itens elegíveis; 548 também no world-group;
- todos não vinculados, negociáveis diretamente e sem mundo oculto;
- piso por item: 10 para 1.292 itens, 30 para 341, 50 para 15, 300 para 31 e
  1.000 para nove;
- preço permitido: 10 até 999.999.999;
- 20 favoritos, 30 registros, 30 resgates e compra máxima de 10.

### Lojas NPC

- 152 produtos em 12 lojas;
- 100% dos produtos e custos resolvidos;
- 44 compras por Crédito, 21 por Moeda da Guilda, 18 N-Token por raça, 16 por
  Moeda de Aventura e 11 por Moeda do Jogo de Guerra;
- recompra: acréscimo bruto 10, prazo 86.400 segundos e máximo 30 itens;
- reset padrão às 05:00.

## Mundo e conteúdo

- 508 mapas;
- 791 regiões habilitadas;
- 7.681 configurações estáticas de spawn;
- 458 regiões permitem voo;
- 74 são ocupáveis;
- 140 têm teleporte condicionado por reino.

### Chefes

`RF_BossSpawn` contém 78 colocações habilitadas, 69 NPCs e níveis 35–123. World
bosses principais:

| Chefe | Nível |
| --- | ---: |
| Vritra | 35 |
| Gleba | 50 |
| Verme de Pedra | 65 |
| EI-01 | 80 |
| Igna Vritra | 95 |
| Blita Gleba | 105 |
| Ragdion | 115 |

O Fantasma da Cidadela (`4504901`, nível 102) é o único random boss com timer
explícito: 7.200.000–10.800.000 ms, isto é, 2–3 horas.

### Masmorras e conflitos

- 15 time dungeons, quatro marcadas como evento;
- todas usam `Use_Charge_Time=3600`;
- quatro graus/mapas de Provas Arcanas;
- cinco graus de Raid de Guilda, recomendação 40/55/65/70/80 e
  25/35/45/45/45 participantes;
- custos brutos do Raid: moeda 504, valores 3k/9k/15k/25k/30k;
- seis mapas de conflito com entrada mínima 45/60/70/70/85/85.

### Quests e eventos

- 1.796 quests e 6.822 alvos;
- 865 links para próxima quest, sem links quebrados ou ciclos;
- cadeia principal estática com 794 quests;
- 195 alvos com limite temporal.

`RF_EventMonsterTable` descreve 15 regiões de evento, cada uma com três etapas
Rakan. Cada etapa cria um chefe e dez auxiliares, tem `DespawnTime=1800` e
`SpawnTime` entre 55 e 63. A tabela não prova que o evento está ativo agora.

### Tri-Placas Dimensionais

Os 48 grupos somam exatamente 100.000.000; nesse sistema específico,
`Rate / 1.000.000` fornece a porcentagem.

- Instável Novus A–C: versões normais aproximadamente 8,636% cada e Mecha
  aproximadamente 0,455% cada;
- Estável Novus A–C: onze versões Mecha aproximadamente 9,091% cada;
- Instável Albern: quatro comuns 23,75% cada e quatro raras 1,25% cada;
- Instável Planeta Exterior: cinco comuns 19% cada e cinco raras 1% cada.

## Superfície de protocolo disponível offline

O `libUnreal.so` contém 1.771 classes de mensagem UTF-16:

| Direção | Classes |
| --- | ---: |
| `FL2C` | 815 |
| `FC2L` | 535 |
| `FG2C` | 274 |
| `FC2G` | 82 |
| `FA2C` | 37 |
| `FC2A` | 28 |

Contagens por tema se sobrepõem, mas mostram a amplitude: 173 mensagens de
item/craft/enchant, 167 de economia/lojas/leilão, 141 de quests/missões, 124 de
combate/skills e 185 de mapa/boss/dungeon.

Prioridades ainda não cobertas pelo decodificador:

- `031b/031c`: status/lista de chefes;
- `031e/031f`: posição de chefe;
- `0330/0331`: status/lista de random bosses;
- `0a01–0a16`: quests;
- `0c01–0c04`: fases e gatilhos do mapa;
- `0c05–0c0a`: world boss, HP, contribuição e ranking;
- `0c0b`, `0c11–0c16`: Raid de Guilda e party dungeon;
- `1702`: agenda de conteúdos;
- `1802/1803`: maior grau de dungeon concluído;
- `1805/1806`: agenda de chefes;
- `1809/180a`: população do conteúdo;
- `1814`: agenda da Nave-Mãe;
- `2301/2302`: exploração de mapa.

Há respostas explícitas do servidor para probabilidades de craft, enchant,
opção, alquimia, talic, remodel e spawn por item. Isso demonstra que as taxas
estáticas desses sistemas podem receber valores em tempo de execução.

## Limites do que pode ser afirmado offline

Não podem ser promovidos a valores atuais/universais sem resposta do servidor:

- chance de loot comum de mobs;
- preços e volume de mercado;
- agenda efetivamente ativa;
- população viva de mapas;
- respawn de mobs comuns;
- ataque/defesa finais de NPCs;
- fórmula final de dano;
- bônus de servidor, evento, conta, grupo ou participação.

O relatório específico de mobs contém HP, EXP, loot observado, cadência e flags
já validados nas capturas existentes: `RFNext-Mobs-EXP-Loot-map.md`.

## Consultas mínimas de reprodução

```sql
-- EXP total da curva
SELECT SUM(PC_NeedExp)
FROM RF_LevelUpTable
WHERE Level BETWEEN 2 AND 200;

-- Fórmulas de status
SELECT s.StatusIndex, p.KO_KR, s.Calculateformula, s.StatCalculate
FROM RF_CharacterTable_StatusTable s
LEFT JOIN RF_StringTable_PT_BR p ON p.StringID=s.StatusNameIndex
WHERE s.Calculateformula <> '';

-- Validação das quatro probabilidades de craft
SELECT COUNT(*) AS receitas,
       SUM(Craft_Result_Normal_Prob + Craft_Result_Better_Prob
           + Craft_Result_Huge_Prob + Craft_Result_Fail_Prob <> 10000) AS invalidas
FROM RF_ItemCraft;

-- Curva de enchant de skill
SELECT EnchantLv, SuccessRate, FailRate_EnchantKeep, FailRate_EnchantDown
FROM RF_SkillEnchantTable
WHERE SkillGroupeIndex=1
ORDER BY EnchantLv;

-- World bosses e níveis
SELECT w.MapContents, w.BossIndex, n.Level, s.KO_KR
FROM RF_WorldBossDungeonMain w
LEFT JOIN RF_NPCTable n ON n.NPCIndex=w.BossIndex
LEFT JOIN RF_StringTable_PT_BR s ON s.StringID=n.NameStringIndex
ORDER BY w.Sort;
```
