# RF QOL 1.0.9 — hotfix do envio do ranking de EXP

Data: 15/08/2026

## Causa confirmada

A versão 1.0.8 decodifica corretamente a resposta `0x1A02` e inicia o envio
automático, mas monta o snapshot com todas as 300 posições presentes no pacote.
O contrato publicado em `POST /api/import/exp-rank` aceita exclusivamente um
Top 100 íntegro e, por isso, responde HTTP 422.

## Correção

- limitar o snapshot às posições `1..100`;
- não combinar escopos ou ciclos diferentes;
- marcar explicitamente capturas completas, parciais e conflitantes;
- enviar somente quando existirem 100 posições únicas do mesmo escopo e ciclo;
- manter capturas parciais locais e pendentes, sem insistir no site a cada ciclo;
- preservar somente campos decodificados, sem payload bruto nem `0x0101`.

## Gates

1. teste unitário com pacote de 300 posições produz exatamente o Top 100;
2. captura parcial não chama o site;
3. o payload produzido passa no validador do contrato ativo;
4. regressão completa do RF QOL;
5. instalador e publicação dependem de autorização específica do owner.
