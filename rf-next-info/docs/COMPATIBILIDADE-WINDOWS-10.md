# Companion: compatibilidade Windows 10

2026-09-06 — beta.43, compatibilidade em teste; não publicada no atualizador.

O pedido atual reabre o suporte ao Windows 10 anteriormente recusado. Alvo de
validação: Windows 10 22H2 x64. Inclui as correções e diagnósticos de equipamentos
da beta.42. A beta.41 pública não inclui esta alteração.

## Caminho implementado

- A seleção verifica as funções da API, não apenas a existência de PktmonApi.dll.
- Quando a API atual está disponível, mantém a captura de streaming existente.
- Sem essas funções, o Agent usa `pktmon.exe` e um consumidor ETW em tempo real.
- O Pktmon usa `--log-mode real-time`, saída descartada e pacotes completos.
  Não usa os modos circular, memory ou multi-file: eles podem gravar ETL.
- Ethernet/TCP filtrado entra no mesmo decoder, filas limitadas e sanitização.
- Nenhum driver adicional, Npcap, hook, exclusão de antivírus ou cópia de DLL do
  Windows 11. Continua exigindo privilégios administrativos.
- A captura global do Pktmon precisa estar livre. Filtros do Companion recebem
  nomes exclusivos; somente esses filtros são removidos.
- Diagnóstico informa `capture.backend`, `backend_error` e `property_errors`.
- Novas portas seguem o reinício controlado de rotas do Agent; não há alteração
  de filtros kernel enquanto a captura de compatibilidade está ativa.
- Falha do consumidor encerra o estado ativo da captura, em vez de manter a UI
  ligada sem receber dados. Exceções não incluem o conteúdo de pacotes.

## Evidências e limites

Os testes cobrem seleção de backend, leiaute x64 do SDK, filtro TCP, timestamp,
eventos incompletos, captura já ocupada, encerramento e limpeza dos filtros.
Resultado direcionado: 55 testes aprovados, incluindo dois clientes passando
pelo callback ETW e pelo decoder real, falha parcial de filtros, erro nativo,
preservação do caminho Windows 11 e diagnósticos pela API local. A regressão
completa e o ensaio do instalador são exigidos pelo build-agent-release.ps1;
build-evidence.json registra o resultado do pacote entregue. Regressão final:
629 testes executados em 96,722 segundos, sem falhas e com 1 ignorado.
A conferência nativa em Windows 11 carregou ETW/TDH e confirmou que OpenTrace
pode retornar um handle antes da existência do logger; a inicialização agora
aguarda o estado ativo do controlador antes de consumir eventos.

Ainda é necessária validação real no Windows 10: início/pausa/retomada, dois
clientes, eventos e equipamentos no site, atraso dos monitores, CPU/RAM e
comportamento ao encerrar o Agent/jogo. Os contadores de perdas da API de
streaming não são equivalentes aos de ETW; zero não comprova ausência de perda
no backend de compatibilidade. Não declarar suporte homologado antes do ensaio.

Instalador beta.43 preparado para teste local; publicação pendente. Nenhuma
alteração no site ou na instalação atualmente em uso. Reversão: reinstalar o
pacote beta.42 no Windows 11 (sem suporte Windows 10). Custo: unknown.

## Referências

- [Pktmon e modo real-time, Microsoft](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-start)
- [Consumo ETW, Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/ns-evntrace-event_trace_logfilew)
- [Eventos e propriedades Pktmon, Microsoft](https://github.com/microsoft/PacketCaptureTools/blob/main/lib/Converter/src/Etl/PktMonConstants.cs)
