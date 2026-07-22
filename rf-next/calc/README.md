# Calculadora de Farms — RF Online Next 1.28.5 (MVP)

Calculadora local+web. `calc/index.html` é **self-contained** (HTML+CSS+JS+dados inline):
abre por duplo-clique (offline) e serve na web igual. Sem backend, sem framework.

## Como usar
Informe **nível do jogador**, **bônus de EXP/crédito do personagem (%)** e **abates por hora**;
busque o mob por nome/nível e selecione. O boost de servidor é preenchido automaticamente pela
faixa do nível do jogador (editável). Saída: EXP/crédito por abate e por hora, tempo para o
próximo nível e até um nível-alvo, e o loot possível.

## Modelo (validado nesta análise)
`EXP_por_abate = floor(exp_base × (1 + boost_servidor(nível) + bônus_personagem))`
- boost de servidor: `RF_BoostSeverTable` (nv≤80 = +35% EXP / +5% crédito, decaindo até nv 91–100).
- Reproduz as capturas: nível 75, +15% de personagem → 16.303 EXP (Ramon), como observado.

## Limites (por design)
- **Chance de drop de mob não é exibida**: é decidida pelo servidor (provado por disassembly).
  A tabela mostra só o **loot possível** (catálogo do cliente).
- Respawn de mob comum e dano/DPS dependem de captura — não são auto-calculados.
- O boost de servidor é indexado pelo **nível do jogador** (a confirmar em captura com jogador
  e mob em faixas diferentes).

## Regenerar os dados
`tools/farm-calc/build_dataset.py` lê `analysis/1.28.5/rfnext-data.sqlite` e gera
`calc/farm_dataset.json`; reinjete no HTML substituindo o bloco `/*__DATASET__*/…/*__END__*/`.
Dataset atual: 2.566 mobs, gerado de 1.28.5.
