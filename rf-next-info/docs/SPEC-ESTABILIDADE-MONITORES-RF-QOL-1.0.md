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
- Permitir que o Monitor PvP opere de 0,5 a 60 segundos, em passos de 0,5
  segundo, com padrão de 1 segundo.
- Verificar o vencimento dos monitores a cada 250 ms, sem sobrepor uma nova
  leitura rápida ao processamento de combate ainda em andamento.
- Atualizar o alvo PvP no intervalo configurado e limitar jogadores próximos,
  tanto na aba quanto nos overlays, a uma reconstrução por segundo.

## Limites

- A captura passiva continua completa e nenhum pacote é descartado pelo modo
  foco.
- O modo foco vem desligado e é persistido por monitor.
- O limite de um segundo se aplica somente às listas de jogadores próximos;
  o alvo atual pode ser atualizado a cada 0,5 segundo.
- Não altera licença, servidor, decoder, instalador ou publicação.

## Aceite local

- regressões específicas para cálculo, expiração, rotas, worker e preferências;
- suíte automatizada integral sem regressão;
- revisão do diff e árvore de trabalho documentada.

## Empacotamento aprovado

- versão `1.0.5`, sequência interna `6`;
- instalador completo NSIS, manual e sem assinatura digital;
- publicação somente na branch órfã `download/rf-qol-1.0.5`, sem GitHub
  Release;
- validação obrigatória do instalador local e do arquivo baixado novamente.

## Resultado do empacotamento

- fonte limpa: `5a702b157eb6873f56117bd0ae5030ae49bd5385`;
- instalador: `RF QOL Setup 1.0.5.exe`, 48.361.534 bytes;
- SHA-256: `1483BD3CD800740F3977F4AFE29B3828BC8A55B42E0299C966510FCC771E168F`;
- assinatura: `NotSigned`;
- publicação: branch órfã `download/rf-qol-1.0.5`, commit `bd1ac85`,
  reconferida pela URL pública.
