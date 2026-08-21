# RF QOL 2.0 — primeira entrega: Ranking de EXP Top 100

Status: implementação local iniciada em 2026-08-14. Sem instalador, publicação ou alteração de produção.

## Objetivo

Entregar a primeira fatia vertical da versão 2.0 usando a leitura passiva já comprovada dos pacotes `0x1A01`–`0x1A04`: armazenar e apresentar no RF QOL o Top 100 oficial de EXP do servidor.

O ranking é global do servidor. Ele não pertence a cliente, personagem ou subsessão e não será usado para classificar subsessões.

## Licenciamento 2.0

- compor, persistir para consumo, exibir ou publicar o Top 100 exige lease v3
  ativa e a feature `exp-ranking`;
- `base` continua cobrindo a EXP das sessões locais, mas não libera o ranking
  oficial do servidor;
- o decoder passivo compartilhado pode reconhecer o protocolo sem criar uma
  captura paralela, porém a ausência de `exp-ranking` bloqueia o consumidor, a
  aba, a API e o envio do ranking;
- a feature não autoriza consulta ativa, automação de cliques nem ranking de
  subsessões.

## Base existente

- O decoder reconhece as mensagens de ranking com confiança `captura-layout-exato`.
- A ingestão registra somente os campos decodificados aceitos pelo contrato local.
- O commit local `8961824` introduziu parser, persistência inicial e envio automático ao site.
- Esta entrega não redefine a semântica dos campos brutos de escopo e ciclo.

## Escopo desta entrega

1. Montar o snapshot mais recente limitado às posições 1–100.
2. Deduplicar repetições idênticas e detectar conflitos de posição ou personagem.
3. Considerar o snapshot completo somente quando as posições 1–100 estiverem presentes e sem conflito.
4. Limitar a composição a eventos do mesmo escopo e ciclo dentro de uma janela local de 15 minutos.
5. Exibir snapshots completos ou parciais numa nova aba local `Ranking de EXP`.
6. Não mostrar UID interno, marca bruta de guilda, identificadores de Profile, escopo bruto ou ciclo bruto na interface.
7. Enviar automaticamente ao site cada snapshot completo novo assim que for
   registrado, com deduplicação por assinatura e nova tentativa após falha.
8. Impedir o envio automático de snapshots parciais ao site.

## Fora do escopo

- Nomear ou mapear o servidor a partir de `scope_id_raw`.
- Alterar a API ou o banco de produção do site.
- Criar histórico, comparação entre ciclos, recompensas ou ranking de subsessões.
- Automatizar cliques, abrir a tela do jogo ou consultar o ranking ativamente.
- Alterar licenciamento, instalador, release, deploy ou distribuição.

## Contrato do snapshot local

O snapshot mantém os campos já consumidos pelo envio existente e acrescenta metadados de integridade:

- `top_limit`: sempre `100` nesta entrega;
- `record_count`: quantidade de posições válidas e únicas;
- `observed_positions`: posições válidas presentes;
- `missing_positions`: posições ainda ausentes;
- `completeness`: `complete` ou `partial`;
- `conflict_count`: quantidade de conflitos detectados;
- `source_pages`: quantidade de eventos que contribuíram para o snapshot;
- `first_captured_at_ns`, `captured_at_ns` e `capture_span_ns`: período observado.

A assinatura de deduplicação representa o conteúdo e a integridade do snapshot, sem depender dos horários de captura.

## Regras de composição

- A mensagem mais recente determina o par de escopo/ciclo selecionado.
- Registros fora desse par são ignorados.
- Registros fora das posições 1–100 são ignorados na lista Top 100.
- Se houver timestamps válidos, somente eventos dentro dos 15 minutos anteriores ao evento mais recente do mesmo par podem contribuir.
- Sem timestamps confiáveis, somente a mensagem mais recente contribui; o resultado permanece parcial, salvo se ela própria trouxer as 100 posições válidas.
- Uma repetição idêntica não é conflito.
- A mesma posição com conteúdo divergente ou o mesmo personagem em posições diferentes torna o snapshot parcial.
- Em conflito, o registro mais recente é exibido, mas a integridade continua marcada como parcial.

## Interface

- Página independente na navegação global: `Ranking de EXP`.
- Tabela: posição, variação, personagem, guilda, nível atual, percentual do
  nível e EXP total.
- Como o pacote `0x1A02` fornece EXP total, mas não nível, nível e percentual
  são derivados deterministicamente com a curva oficial `1.28.5` embarcada;
  a interface identifica essa origem e não atribui o cálculo ao protocolo.
- Busca local por personagem ou guilda.
- Estado vazio explica que o usuário deve abrir e percorrer o ranking no jogo enquanto o RF QOL observa passivamente.
- Estado parcial informa quantas posições foram capturadas e quais ainda faltam, sem alegar completude.
- A interface permanece em português; nomes do jogo não são traduzidos pela UI.

## Critérios de aceite

- Um conjunto válido das posições 1–100 gera `completeness=complete`.
- Uma ou mais posições ausentes, duplicadas de forma conflitante ou fora da janela geram `completeness=partial`.
- Eventos de outro escopo/ciclo não contaminam o snapshot atual.
- A interface nunca mostra os identificadores internos presentes no registro armazenado.
- Nível e percentual exibidos devem corresponder à EXP total e à curva 1.28.5;
  valor inválido ou curva indisponível permanece `—`.
- O envio automático ignora snapshots parciais.
- Um snapshot completo novo dispara envio automático ao site; a mesma assinatura
  não é reenviada após confirmação, e uma falha não marca o snapshot como enviado.
- Ausência de `exp-ranking` bloqueia aba, API, envio e operações diretas sem
  bloquear a EXP local coberta por `base`.
- Testes do parser, armazenamento, leitura, interface e envio continuam passando.

## Rollback

O recorte é aditivo. O rollback consiste em remover a página e os metadados novos do snapshot e restaurar a montagem simples anterior; nenhuma migração de banco é necessária.
