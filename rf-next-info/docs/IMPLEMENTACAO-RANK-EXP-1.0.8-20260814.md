# RF QOL 1.0.8 — decoder e envio automático do ranking de EXP

Data: 14/08/2026

## Escopo entregue

- portado do decoder canônico o protocolo de ranking de EXP `0x1A01` a
  `0x1A04`, preservando as correções já presentes na 1.0.8 para alvo atual,
  desaparecimento, teleporte e equipamentos;
- respostas `0x1A02` são consolidadas por escopo e ciclo, validadas e
  sanitizadas antes do envio;
- são enviados UID, personagem, guilda, marca da guilda, EXP total, posição
  atual e anterior; a resposta individual `0x1A04` é associada ao mesmo ciclo;
- campos internos de Profile do protocolo e qualquer pacote bruto ficam fora
  do envio;
- uma assinatura estável impede o reenvio da mesma fotografia, inclusive em
  outra sessão;
- falhas usam espera de 60 segundos e só registram o lote como enviado quando
  o site confirma exatamente a quantidade recebida.

## Contrato do site

- rota dedicada: `POST /api/import/exp-rank`;
- autenticação: token do Profile e lease ativa já usados pelo RF QOL;
- idempotência: cabeçalho `Idempotency-Key` SHA-256;
- persistência preparada em `exp_rank_snapshots` e `exp_rank_entries`;
- o uso de rota dedicada impede que um servidor antigo aceite e descarte os
  dados silenciosamente.

O contrato e a persistência foram implementados localmente em
`K:\MCP\Karvalho\rf-next\app\server.py` e passaram no `--self-test`. O serviço
de produção não foi reiniciado nem publicado nesta tarefa. Até a promoção do
backend, o cliente mantém o lote pendente e tenta novamente; não informa falso
sucesso.

## Validação

- decoder: `self-test: ok`;
- servidor: `OCR parser OK`, incluindo persistência e idempotência do ranking;
- RF QOL: duas regressões completas e a regressão do build, cada uma com 265
  testes aprovados;
- executável empacotado: autoteste aprovado;
- instalador: instalação, autoteste pós-instalação e desinstalação aprovados;
- Authenticode: `NotSigned`, conforme decisão do owner;
- commit de implementação: `89618246891d70ada81502975327f9900042ef1d`;
- instalador: `RF QOL Setup 1.0.8.exe`, 48.374.153 bytes;
- SHA-256: `6495A27AA653246823B56A6159AD9601C7BFCB9293077E15916CED1DCCF045D2`.

## Publicação

O instalador substitui o arquivo da branch órfã
`download/rf-qol-1.0.8`, sem GitHub Release. O link permanece:

`https://github.com/Carvalho3009/RFNextInfo/raw/refs/heads/download/rf-qol-1.0.8/RF%20QOL%20Setup%201.0.8.exe`
