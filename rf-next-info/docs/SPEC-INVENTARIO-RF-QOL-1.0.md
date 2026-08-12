# Inventário no RF QOL 1.0

Estado: implementação local validada em 2026-08-11. Não publicado.

## Objetivo

- Reconstruir passivamente o inventário de cada personagem identificado.
- Exibir item, ícone, quantidade, tipo e slot na aba **Inventário**.
- Separar a lista nas subabas **Equipamentos**, **Consumíveis**,
  **Materiais**, **Talicas**, **Partes de Rover** e **Outros**.
- Manter PC e Emuladores separados pelos sete slots já existentes.
- Preparar o inventário sanitizado dentro do envio de Personagem ao site.

## Fonte e confiança

O decoder embutido reutiliza o suporte canônico validado em
`rf-next/analysis/1.28.5/rfnext_frame_decode.py` para:

- snapshots `0x0401` (empilháveis) e `0x0403` (equipamentos);
- deltas `0x0402` (empilháveis) e `0x0404` (equipamentos).

Armazém (`0x1F05` a `0x1F08`) é reconhecido pelo decoder, mas fica fora da
interface e do envio desta entrega.

## Reconstrução

- Cada snapshot substitui somente a classe recebida (`stackable` ou
  `equipment`).
- Cada delta substitui o item da mesma classe no slot recebido.
- Quantidade zero remove o item.
- O resultado é associado ao personagem pelo roteamento de fluxo já usado
  pelo RF QOL.

## Privacidade e envio

O programa guarda o evento decodificado no banco local existente. O contrato
preparado para o site envia somente:

`item_index`, `name`, `quantity`, `kind`, `slot`, `refinement`, `locked` e
`expires_at`.

UID de instância do item, payload bruto, IP, token, ticket e `0x0101` não são
incluídos no objeto `capture.inventory`.

O site ainda precisa de uma mudança própria para persistir e apresentar o
novo campo; até lá, servidores antigos podem ignorá-lo sem quebrar o envio de
Personagem.

## Ícones

Os ícones são miniaturas WebP de 64 px geradas a partir do catálogo local
canônico e empacotadas em um único arquivo ZIP. Item sem imagem usa o ícone
neutro da interface.

O nome respeita o idioma configurado. Se o catálogo principal não tiver a
tradução daquele código, o programa usa o outro catálogo antes de exibir
`Item <código>`; assim, itens conhecidos não perdem o nome apenas por ainda
não possuírem tradução portuguesa.

## Categorias

Cada código aparece em exatamente uma subaba. A classificação foi gerada a
partir de `RF_ItemTable.RFTable` e `RF_ItemTypeDefine_Table.RFTable` oficiais
da versão 1.28.5, sem depender do nome localizado do item.

A precedência é:

1. tipos oficiais 2074 e 2082: Partes de Rover;
2. categorias de equipamento 1 a 4 ou `EquipPartType` definido: Equipamentos;
3. categoria 5 ou `TalicColor` definido: Talicas;
4. categoria 7 ou grupos oficiais de armazém 2, 3 e 6: Materiais;
5. tipo marcado pelo jogo como utilizável: Consumíveis;
6. demais itens: Outros.

Um código ausente do catálogo fica em **Outros**; somente um registro bruto
explicitamente identificado como equipamento usa **Equipamentos** como
fallback. A pesquisa por nome ou código atua somente dentro da subaba e do
cliente atualmente selecionados.

## Validação local

- catálogo conferido com 8.231 códigos e uma categoria por código;
- regressão dedicada cobrindo as seis categorias e o fallback;
- interface validada alternando Materiais e Equipamentos no mesmo cliente;
- suíte completa: 230 testes aprovados e 1 ignorado por indisponibilidade da
  área de notificação no ambiente de teste.
