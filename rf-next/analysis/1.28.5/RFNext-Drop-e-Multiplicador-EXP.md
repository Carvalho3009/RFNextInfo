# RF ONLINE NEXT 1.28.5 — Sorteio de drop e multiplicador de EXP

Data: 2026-07-22 · Fontes: `libUnreal.so` (disassembly capstone) + `rfnext-data.sqlite`.
Modo offline: sem captura nova, sem runtime.

## Item 1 — Sorteio de drop de mob: é 100% servidor (resultado definitivo)

**Conclusão:** o cliente **não sorteia** o loot de mob. Ele apenas monta a lista de candidatos.

Evidência estática (encerra a dúvida que ficou aberta nas rodadas anteriores):

- As duas funções que consultam recompensa — `0x06784d54` (`WHERE RewardIndex={0}`) e
  `0x06784f08` (`WHERE SubGroupIndex={0}`) — têm **19 call-sites** em **9 funções** distintas.
- Disassembladas as 9: **zero** operações de ponto flutuante (`fmul/fdiv/fadd/fcvtzs`),
  **zero** comparações `fcmp` e **nenhuma** chamada a RNG. O padrão é sempre o mesmo:
  percorrer `RewardIndex` → para cada linha, consultar `SubGroupIndex` → copiar **todas** as
  linhas de item para uma lista de saída (memcpy). Não há peso, percentual nem roleta.
- Somado ao já sabido (as tabelas `RF_RewardTableRow`/`RF_SubGroupInfoRow` não têm coluna de
  probabilidade; todos os `BoxType` alcançados = `ITEM_REWARD_BOX_TYPE_NONE`), fica provado:
  a seleção do que cai é decidida pelo servidor.

**Implicação para a calculadora:** não prometer “chance de drop %” de mob a partir do cliente.
O que dá para expor com segurança é **loot possível por mob** (catálogo estático) + **taxas
empíricas** medidas nas capturas (com intervalo de confiança e nº de abates). As roletas que
*têm* odds no cliente (craft, alquimia, enchant, opção, talic, remodel Prime, Tri-Placas) seguem
válidas e já documentadas — o drop de campo é a exceção sem odds estáticas.

## Item 2 — Multiplicador dinâmico de EXP: identificado e reconciliado

**Conclusão:** o ganho não é um multiplicador fixo. É a soma de um **stat percentual de ganho de
EXP** (`STAT_EXPDROPINCRATE`, índice 90, PT-BR “Ganho de EXP”) vindo de duas camadas:

```
EXP_ganho = floor( EXP_base × (1 + ΣEXPDROPINCRATE / 10000) )
```

1. **Boost de servidor** — tabela `RF_BoostSeverTable`, por faixa de nível (sempre ativa /
   catch-up; há também o evento “Hot Time / Impulso de EXP”, string `ui_boost_hottime`):

   | Faixa de nível | EXP (`ExpBuffValue`) | = % | Gold (`GoldBuffValue`) |
   | --- | ---: | ---: | ---: |
   | 1–80 | 3500 | +35% | 500 (+5%) |
   | 81–84 | 3000 | +30% | 500 |
   | 85–86 | 2500 | +25% | 500 |
   | 87–88 | 2000 | +20% | 500 |
   | 89–90 | 1500 | +15% | 500 |
   | 91–100 | 1000 | +10% | 500 |

   (Valores em base 10000 → `valor/10000` = fração; `StatType` 87 carrega EXP, 86 carrega Gold.)

2. **Bônus por personagem** — o mesmo stat 90 é concedido por dezenas de fontes: opções de
   biosuit (`RF_BiosuitEnchantOption`), coleções de item/biosuit (`RF_ItemCollection`,
   `RF_Collection_PartReward`, 90+ linhas), opções de item (`RF_ItemOptionTable`), id card,
   costume e ultimate gear. Cada fonte soma pontos; o total varia por conta/equipamento.

**Reconciliação com as duas capturas** (valida o modelo — o resíduo por personagem sai redondo):

| Amostra | EXP base | EXP observada | Multiplicador | = Servidor +35% + Personagem |
| --- | ---: | ---: | ---: | --- |
| Cliente A (mobs nv 70) | 9.669 | 14.986 | ×1,5499 | +35% + **+20,0%** |
| Cliente B (mobs nv 75) | 10.869 | 16.303 | ×1,5000 | +35% + **+15,0%** |

O mesmo esquema explica o crédito (stat 89 `STAT_CREDITDROPINCRATE`, Gold buff +5%):
A ×1,064 = +5% + ~1,4%; B ×1,078 = +5% + ~2,8%.

**Implicação para a calculadora:** modelar EXP/h como `EXP_base × (1 + boost)`, onde `boost` é
**parâmetro** (não constante): `boost = boost_servidor(faixa de nível) + bônus_do_personagem`.
O `boost_servidor` sai direto de `RF_BoostSeverTable`; o `bônus_do_personagem` é entrada do
usuário (ou lido por captura/telemetria). Assim a calculadora fica correta para qualquer conta,
sem “chumbar” 1,5×.

## Status offline

- Drop de mob (%): **encerrado offline** — é servidor; só amostragem por captura refina.
- Multiplicador de EXP: **mecanismo e fórmula resolvidos**; o componente por-personagem precisa
  do inventário/coleções do jogador (entrada) para o número exato de cada conta.
