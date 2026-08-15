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

## Resultado da release

- autorização do owner recebida em 15/08/2026;
- versão `1.0.9`, sequência interna `10`;
- 266 testes aprovados no build de release;
- executável empacotado e smoke de instalação, autoteste e desinstalação
  aprovados;
- instalador `RF QOL Setup 1.0.9.exe`, 48.373.255 bytes;
- SHA-256
  `E4B2E32650114FA062AC7FD4EE8289B4147E9A2BAB29758D680A335F71216D9F`;
- ProductVersion e FileVersion `1.0.9`; Authenticode `NotSigned`;
- código do hotfix: `9cd59fc`; preparação da release: `d60048c`;
- artefatos publicados em `download/rf-qol-1.0.9`, commit `f4240ae`;
- download público refeito e validado com os mesmos bytes, hash, versão e
  estado de assinatura;
- link:
  `https://github.com/Carvalho3009/RFNextInfo/raw/refs/heads/download/rf-qol-1.0.9/RF%20QOL%20Setup%201.0.9.exe`.
