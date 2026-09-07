# Companion: compatibilidade Windows 10

2026-09-07 UTC — beta.43 publicada no atualizador; compatibilidade Windows 10 em teste.

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

Instalador beta.43 publicado no canal beta, sequência 53. Nenhuma
alteração no site ou na instalação atualmente em uso. Reversão: reinstalar o
pacote beta.42 no Windows 11 (sem suporte Windows 10). Custo: unknown.

## Correcao beta.45: texto do Pktmon

07/09/2026 UTC — publicada na beta.45, sequencia 55, com autorizacao do owner.

O computador afetado mostrou `O Monitor de Pacotes nao esta em execucao.`
com os acentos corretos no console, enquanto o Agent bloqueava como ocupado
ou desconhecido. A frase Unicode correta ja era aceita. Foi reproduzido o
defeito lendo bytes OEM como ANSI/UTF-8: a conversao alterava os acentos antes
de verificar o estado. O screenshot nao permite confirmar a pagina de codigo
exata do computador remoto, e nao substitui a validacao do novo executavel la.

- O caminho ETW do Agent preserva a resposta em bytes, sem `errors=replace`.
- O parser existente considera UTF-8 e as paginas OEM/ANSI do proprio Windows,
  com decodificacao estrita. Mantem o contrato para os chamadores com strings.
- Iniciar e aguardar o stream usam o mesmo parser corrigido. Estado ocupado,
  vazio, desconhecido ou com interpretacoes conflitantes continua bloqueado;
  nenhuma captura de terceiros e parada ou tem filtros removidos.
- Teste com subprocesso real oculto imprime somente frases fixas PT/EN nas
  tres codificacoes, sem executar Pktmon. Inicio, abertura ETW e encerramento
  sao exercitados com controlador simulado, preservando os filtros alheios.
- Validacao direcionada: 33 testes OK; os 14 testes ETW tambem passaram com
  `python -X utf8`. Regressao final: 637 testes em 80,254 s, sem falhas, 1 skip
  opcional preexistente; replay privado de equipamentos habilitado.

Correcao originada em `fix/pktmon-windows-console-encoding`, publicada por
`release/rf-qol-agent-beta45`. Nenhuma mudanca no decoder, protocolo, servidor ou
captura em uso. Instalador isolado, modulos empacotados, download publico e
atualizador validados; evidencias em `RELEASE-AGENT-BETA45.md`.
Proximo gate: testar no Windows 10 afetado apos atualizar. Rollback: artefato e
manifesto beta.44 preservados; nao ha downgrade automatico. Custo real: unknown.

## Referências

- [Pktmon e modo real-time, Microsoft](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-start)
- [Consumo ETW, Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/ns-evntrace-event_trace_logfilew)
- [Eventos e propriedades Pktmon, Microsoft](https://github.com/microsoft/PacketCaptureTools/blob/main/lib/Converter/src/Etl/PktMonConstants.cs)
- [Codecs OEM e ANSI do Windows, Python](https://docs.python.org/3.13/library/codecs.html#python-specific-encodings)
