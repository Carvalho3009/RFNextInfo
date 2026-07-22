# NOTAS — Codex parcial (RF Next)

Gerado por `build_codex_dataset.py` a partir dos exports 1.28.5 + captura de mercado.

## Contagens do dataset (verificadas)
- collections: **4503** (bate com collections.csv)
- reqs / slots ativos (ItemGroup != 0): **13781**
- pares de preço na captura: **2686** (fonte: exchange, última ocorrência de cada par item_ench)
- slots com preço resolvível (algum item aceito tem preço no encanto exigido): **4858**
- groups (ItemGroups distintos): 2724
- stats usados: 117 (só os referenciados em rw/prw/typeRewards)
- typeRewards: só CollectionType **1** — ver pendência abaixo
- cols com reward-stat (rw): 4503 (todas) | cols com part-rewards (prw): 1986
- ev=1 (PeriodCollection): 97 | chip: {0:4383, 1:24, 2:32, 3:39, 4:11, 5:14}
- JSON final: **978.802 bytes (~0,93 MB)** — bem abaixo da meta de ~2 MB (minificado, sem espaços)

## Decisões
- Encanto do slot = coluna `Collection{n}_EnchantLevel`. A variante com typo `Collectrion{n}_EnchantLevel` é 100% zero → ignorada. Cross-check com `RequiredEnchantLevel` de collection_requirements: **0 divergências** em 13781 slots.
- Nomes de itens NÃO repetidos em cada req: ficam só em `groups` (minificação pedida na spec).
- Preço: exchange preferida; fallback `market.csv` (mesmos 2686 pares) se exchange ausente/vazia. Preço sempre `lowest_price` (menor preço). Nunca estimado.
- Preço de slot = min(prices[ai_ench]) sobre os itens aceitos do grupo, no encanto do slot; sem par → null (pendência visível, nunca estimativa).
- `stats`, `groups`, `typeRewards` com chaves string (JSON não aceita chave int).

## Pendências (dado ausente = pendência visível)
- **typeRewards só cobre CollectionType 1** (423 linhas em collection_complete_rewards.csv, todas tipo 1). Coleções tipo 2 NÃO têm reward de conclusão neste export → a UI deve exibir "recompensa de conclusão indisponível" para tipo 2, não inventar.
- ~64,7% dos slots ativos (13781−4858 = 8923) ficam SEM preço na captura atual → aparecem como pendência de preço no custo. Captura de mercado mais ampla reduz isso.
- ponytail: fallback market.csv é snapshot único sem histórico por opcode; upgrade = mesclar várias capturas por mtime.
- ponytail: storage do CodexProfiles é detectado uma vez na construção; não reage a localStorage que some/volta em runtime.

## Testes
`node test_codex_core.js` → **33 passed, 0 failed**. Cobre: custo com/sem preço e com slot marcado, encanto exigido, filtro por texto acento-insensível (nome de coleção e de item), filtros chip/ev/tipo/buyable/status, sort por custo asc/desc com nulls no fim, sort name/game, e roundtrip export/import de profile (+ rename/delete/setMark).
