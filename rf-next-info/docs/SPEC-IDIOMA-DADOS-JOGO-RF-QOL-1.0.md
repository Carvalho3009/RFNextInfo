# Idioma dos dados do jogo no RF QOL 1.0

Estado: implementado e validado localmente em 2026-08-11. Não publicado.

## Escopo

A preferência **Idioma dos dados do jogo** aceita Português (`pt`) e English
(`en`). Ela altera somente nomes e classificações provenientes do RF NEXT.
A interface, os botões, os avisos e as mensagens do RF QOL permanecem em
português.

São cobertos:

- itens de loot, inventário, equipamento e Mercado;
- mapas, spots e mobs;
- bosses;
- Biosuits e Rovers;
- dados preparados para exportação e envio ao site.

## Regra de resolução

1. Usar o catálogo do idioma selecionado.
2. Se o código conhecido não tiver nome nesse catálogo, usar o outro idioma.
3. Somente quando os dois catálogos não tiverem o código, mostrar o
   identificador genérico já usado pelo programa.

A mesma resolução é usada na tela, nos overlays que exibem dados do jogo, nos
arquivos exportados e nos payloads enviados ao site. A troca da preferência
recarrega o snapshot visível e preserva o mesmo mapa/spot quando existe a
correspondência no outro idioma.

## Fontes

- itens: `core/item_names.json` e `core/item_names_en.json`;
- mapas, spots e mobs: `core/catalogo.csv` e `core/catalogo_en.csv`;
- bosses: campos `name_ptbr` e `name_en` de `core/boss_catalog.csv`;
- Biosuits e Rovers: nomes PT/EN extraídos das tabelas oficiais 1.28.5 e
  registrados em `core/biosuits.json` e `core/rovers.json`.

## Aceite

- um item existente nos dois catálogos muda conforme a preferência;
- um item ausente em Português continua identificado pelo nome inglês;
- mapas, spots, mobs e bosses seguem a mesma preferência;
- Biosuits e Rovers com nomes diferentes entre os idiomas são localizados;
- a interface continua em português;
- exportação e envio usam o mesmo idioma que a exibição.
