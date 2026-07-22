# Mockup navegável — Guia ROOC Americas

## Abrir

Abra [`index.html`](./index.html) em um navegador moderno. Não há instalação, build ou servidor obrigatório.

## Entregáveis visuais

- [`rooc-karvalho-home-desktop.png`](./rooc-karvalho-home-desktop.png) — conceito do primeiro viewport desktop.
- [`rooc-karvalho-secoes-desktop.png`](./rooc-karvalho-secoes-desktop.png) — conceito das seções de classes, progressão e agenda.
- [`rooc-karvalho-home-mobile.png`](./rooc-karvalho-home-mobile.png) — conceito do primeiro viewport móvel.
- [`render-desktop.png`](./render-desktop.png) — captura completa do protótipo implementado.
- [`render-mobile.png`](./render-mobile.png) — captura móvel completa do protótipo implementado.

## Sistema visual aplicado

- Carvão: `#070909`
- Osso: `#F4F2EB`
- Ouro: `#D4A64D`
- Ácido: `#A8FF16`
- Coral: `#FF6547`
- Água: `#63B9F3`
- Display: Bahnschrift Condensed/Bahnschrift
- Texto: Segoe UI/Inter

## Interações implementadas

- menu móvel acessível com `aria-expanded`;
- navegação por âncoras;
- filtros das 14 classes;
- detalhe da classe selecionada com região viva;
- tabela com rolagem própria em telas estreitas;
- respeito a `prefers-reduced-motion`.

## Viewports verificados

- Desktop: `1440 × 900`, sem overflow horizontal.
- Mobile: `390 × 844`, sem overflow horizontal; hero termina em `832 px`; controles principais com pelo menos `44 px`.

O protótipo usa somente HTML, CSS e JavaScript nativos.
