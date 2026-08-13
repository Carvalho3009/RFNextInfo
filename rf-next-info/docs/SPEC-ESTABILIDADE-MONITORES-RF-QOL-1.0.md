# Estabilidade dos monitores — implementação aprovada

Data: 13 ago 2026  
Estado: aprovado para implementação local pelo owner

## Escopo

- Calcular o DPS por guilda com todos os eventos da janela, sem reconstruí-lo
  a partir do ranking limitado de jogadores.
- Recusar a atribuição quando dois clientes da mesma família não puderem ser
  separados por processo e porta.
- Remover bosses sem confirmação recente dos snapshots, alertas e overlays.
- Garantir que um worker de stream termine antes que outro possa substituí-lo.
- Rotear os eventos uma única vez por cliente e resumir somente PvE, PvP e
  Boss que estejam ligados.
- Adicionar `Modo foco` independente em PvP e Boss. Quando o modo correspondente
  estiver marcado e o monitor ligado, a leitura geral passa para 300 segundos;
  todos os monitores ligados mantêm seus próprios intervalos rápidos.

## Limites

- A captura passiva continua completa e nenhum pacote é descartado pelo modo
  foco.
- O modo foco vem desligado e é persistido por monitor.
- Não altera licença, servidor, decoder, instalador ou publicação.

## Aceite local

- regressões específicas para cálculo, expiração, rotas, worker e preferências;
- suíte automatizada integral sem regressão;
- revisão do diff e árvore de trabalho documentada.
