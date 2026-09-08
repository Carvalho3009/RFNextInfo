# Auditoria do Companion beta.45 — Windows 10

Data: 08/09/2026. Estado: auditoria de código e reproduções automáticas concluídas; correções propostas, ainda não implementadas. Validação no computador Windows 10 afetado continua pendente.

## Conclusão

A beta.45 contém falhas capazes de deixar a janela aberta com captura aparentemente ativa, interromper a geração de eventos de uma conexão ou bloquear permanentemente os envios depois de uma falha local temporária. Não é correto considerar a estabilidade resolvida apenas porque o Agent abre no Windows 10 ou porque a suíte existente passa.

Foram reproduzidos **dez cenários de falha**. Os mais relevantes para “funciona e depois para” são a sequência TCP ao dar a volta, o reaproveitamento de uma conexão, o acúmulo de portas, a recuperação incompleta da captura e o bloqueio da entrega. Parte é específica do caminho Pktmon/ETW usado no Windows 10; parte está no código compartilhado e também pode afetar o Windows 11.

**Isso não identifica, por si só, qual desses caminhos ocorreu no computador do usuário.** Não recebi um diagnóstico/log capturado durante a falha desse Windows 10. Não houve acesso a essa máquina, ensaio prolongado nela ou reprodução nativa do travamento relatado.

## Base e limites

| Item | Evidência |
| --- | --- |
| Produto | RF Next Companion `2.0.0-beta.45`, sequência de atualização 55 |
| Checkout | `K:\MCP\_release-builds\rf-qol-agent-2.0.0-beta.45\rf-next-info` |
| HEAD auditado | `626ab4e4677512ba98d6c54eb4af3ac80ec6a51d` |
| Commit do código empacotado, conforme registro da release | `7331f806714b2f0f899f7966d533d1e1d362cc0d` |
| Branch desta auditoria | `audit/windows10-beta45-stability` |
| Alvo | Windows 10 22H2 x64; captura passiva pelo fallback Pktmon/ETW |
| Ambiente dos testes desta auditoria | Windows 11 build 26200, Python 3.13.5; captura nativa simulada nas reproduções |
| Alterações realizadas | Este relatório e um script de reprodução; nenhum arquivo de produção alterado |
| Não realizado | Instalador novo, publicação, alteração no servidor, controle visual, reinício do Agent/jogo ou alteração deliberada de captura em uso |

A auditoria abrange o fluxo do Agent: descoberta de clientes → captura → remontagem TCP → decoder → projeção → outbox → entrega/API local → interface e encerramento. O programa Desktop antigo, o processamento interno do site e o bot Discord não receberam uma auditoria funcional própria. A regressão existente contém testes adicionais do Desktop, mas isso não transforma este trabalho em homologação de todos esses produtos.

## Resultados executados

| Verificação | Resultado nesta execução |
| --- | --- |
| Regressão automática existente | **637 testes em 64,452 s: 636 aprovados, zero falhas, um ignorado** |
| Captura ETW e runtime Windows, seleção específica | **32 testes aprovados em 2,446 s**; fazem parte da suíte, não são 32 testes adicionais distintos |
| Replay privado de equipamentos | Habilitado na regressão; captura lida localmente, sem copiar o tráfego para o relatório |
| Provas de falha desta auditoria | **10/10 cenários reproduzidos**; isto confirma defeitos, não aprovação do produto |
| Teste físico no Windows 10 | Não executado |
| Uso contínuo real por várias horas | Não executado |

O teste ignorado é o de ciclo da área de notificação, indisponível no ambiente de testes. Os rastros de “falha ao iniciar captura” emitidos durante a suíte incluem cenários negativos esperados; as tentativas nativas não elevadas retornaram acesso negado. Não foram tratadas como prova de captura real funcionando.

A correção de codificação da beta.45 continua coberta: respostas PT/EN em bytes, OEM/ANSI/UTF-8 e bloqueio diante de estado ocupado/desconhecido. Ela resolve o erro anterior de interpretação de texto; **não resolve as falhas de continuidade encontradas abaixo**.

## Falhas reproduzidas e correções propostas

P1 = corrigir antes de afirmar estabilidade ou distribuir uma correção de continuidade. P2 = corrigir no ciclo de robustez; pode causar perda ou aparente travamento em condições específicas. As prioridades indicam impacto, não frequência medida na máquina afetada.

### A01 — P1: sequência TCP dá a volta e a conexão deixa de gerar eventos

Local: [live_stream.py:340](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/core/live_stream.py:340). Prova: `TCP_WRAP`.

`next_sequence` cresce como inteiro ilimitado, enquanto o pacote carrega sequência de 32 bits. Após a volta para zero, `end <= expected` classifica os novos dados como retransmissões antigas e os descarta. Não há segmento pendente para acionar a recuperação de lacunas.

Resultado: um evento antes da volta; **zero eventos nos cinco frames válidos seguintes**; o mesmo frame gera um evento em decoder novo. Outro fluxo continua gerando eventos. O contador de fluxos travados fica em **zero**. A falha pode durar enquanto o contexto TCP permanecer no decoder.

Correção: normalizar a sequência em relação ao ponto esperado, com aritmética modular de 32 bits, incluindo sobreposição e segmentos fora de ordem. Não basta aplicar `% 2**32` somente no contador; as comparações também precisam respeitar o ciclo. A regra está na [RFC 9293, seção 3.4](https://www.rfc-editor.org/rfc/rfc9293.html#section-3.4).

Aceite: fluxo cruzando o limite com frames inteiros/partidos, duplicatas, sobreposição e segmentos fora de ordem; segundo cliente simultâneo deve permanecer independente. Não associar o problema a uma duração fixa: o ponto inicial de sequência e o volume de tráfego variam.

### A02 — P1: uma conexão reutilizada pode herdar a sequência antiga

Local: [live_stream.py:107](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/core/live_stream.py:107), `feed` e `_append_segment`. Prova: `TCP_RECONNECT`.

Pacotes SYN/RST/FIN sem payload não chegam ao controle de vida do fluxo. Se o mesmo par de endereços/portas reaparece com nova sequência, ainda no contexto retido, os dados podem ser descartados como antigos. Vincular a identidade ao PID não resolve a geração da conexão TCP.

Resultado: SYN sintético de reconexão seguido de cinco frames válidos produz **zero novos eventos**; decoder novo lê o mesmo frame. Outro fluxo permanece funcionando.

Correção: reconhecer os sinais de abertura/encerramento antes do filtro de payload e invalidar somente a geração TCP afetada. Conservar a identidade confirmada do personagem quando apropriado, sem conservar a remontagem da conexão anterior. Não reiniciar o decoder inteiro em todo teleporte ou período sem EXP.

Aceite: reconexão com sequência menor/maior, portas reutilizadas, mesmo PID, novo PID, SYN retransmitido e captura iniciada no meio de uma conexão; sem misturar clientes.

### A03 — P1: falha ao trocar rotas deixa “capturando” falso e duplica métricas

Locais: [windows_agent_capture.py:512](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/core/windows_agent_capture.py:512), `active` e `health`. Prova: `ROUTE_STOP_FAILURE`.

O runtime soma as métricas do backend antigo e chama `previous.stop()` fora do bloco de recuperação. Se `stop` falha depois de parar a captura, `live_capture` continua apontando para o objeto antigo. `active` só verifica a existência desse objeto.

Resultado: captura antiga parada, estado **`capturing`**, `last_error` vazio e **14 pacotes informados para sete reais**. A tentativa de restauração nem é alcançada.

Correção: proteger toda a transição; refletir o estado real do backend, consolidar contadores uma única vez e preservar a sessão/outbox quando apenas a captura for substituída. Se a limpeza ficar pendente, mostrar esse estado e não alegar captura ativa nem iniciar um consumidor conflitante.

Aceite: falhas em stop, criação e start do substituto, restauração bem-sucedida e restauração falhando; contadores exatos e mesma sessão quando a recuperação for possível.

### A04 — P1: portas antigas acumuladas esgotam os filtros nativos

Locais: [windows_agent_capture.py:580](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/core/windows_agent_capture.py:580) e [pktmon_etw.py:207](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/core/pktmon_etw.py:207). Prova: `NATIVE_FILTER_LIMIT`.

As portas são acumuladas até o fim da captura, inclusive portas locais obsoletas. O fallback ETW cria um filtro por porta. O Pktmon permite **até 32 filtros ativos no total**, incluindo filtros de outros usos. [Documentação Microsoft](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-filter-add).

Resultado simulado com dois clientes e 38 mudanças de pares de portas: **64 tentativas de início, 25 falhando**, solicitação de até 34 portas e restauração de um conjunto antigo com 32. As portas iniciais obsoletas continuam retidas. O limite nativo foi modelado no teste; não esgotei filtros reais da máquina.

Isso comprova repetição de falhas/reinícios, não que toda comunicação necessariamente pare: uma porta de servidor já coberta pode continuar recebendo tráfego.

Correção: evitar reinícios quando o filtro atual já cobre a rota; preferir portas remotas estáveis confirmadas. Quando forem necessários filtros locais, manter somente rotas ativas mais uma tolerância curta e limitada. Verificar capacidade global antes de parar a captura, sem remover filtros alheios e sem descartar arbitrariamente portas de um cliente. Dois argumentos `-p` significam correspondência de ambas as portas, não uma lista OR ilimitada.

Aceite: dezenas de reconexões, dois ou mais clientes, filtros de terceiros e novas portas não cobertas; quantidade limitada, sem ciclo infinito de tentativas e sem lacunas evitáveis.

### A05 — P1: erro durante a limpeza deixa recursos nativos pendentes

Local: [pktmon_etw.py:220](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/core/pktmon_etw.py:220). Prova: `CLEANUP_FAILURE`.

Se o comando stop falhar e `process.terminate()` também lançar erro, o restante da limpeza não executa. Há ainda caminhos que descartam referências após timeout sem comprovar o término do controlador/consumidor.

Resultado: `CloseTrace` não chamado e filtro próprio não removido, com todas as chamadas nativas simuladas.

Correção: liberar cada recurso em blocos independentes de limpeza, acumular erros e manter referências/callbacks enquanto o consumidor existir. Conferir o retorno de `CloseTrace`; `ERROR_CTX_CLOSE_PENDING` significa fechamento aceito, mas ainda drenando buffers, e não erro definitivo. Esperar com limite e conservar propriedade para uma tentativa segura posterior. [Microsoft: CloseTrace](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/nf-evntrace-closetrace).

Aceite: controlador encerrado inesperadamente, timeout, erro de terminate, fechamento ETW pendente e falha ao remover filtro. Nunca usar `pktmon stop`/limpeza global indiscriminada para recuperar uma captura de propriedade desconhecida.

### A06 — P1: erro local temporário bloqueia o envio sem recuperação

Local: [web_agent_transport.py:730](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/core/web_agent_transport.py:730), especialmente tratamento genérico em `send_once`. Prova: `TRANSIENT_DELIVERY_FAILURE`.

Uma exceção local não classificada define `_blocked=True`. Esse estado não tem recuperação no mesmo objeto; `start()` não o limpa. Portanto, nem toda parada de envio depende de problema no receptor.

Resultado: simular `sqlite3.OperationalError("database is locked")`, depois disponibilizar novamente o banco, mantém estado **`blocked` / `local_delivery_error`**. A chamada seguinte não tenta ler o banco recuperado.

Correção: distinguir falhas locais temporárias conhecidas de corrupção, contrato inválido e revogação. Aplicar tentativa posterior limitada às transitórias, conservando lote/ordem/idempotência. Manter bloqueio seguro para corrupção/autorização inválida. Proteger também a leitura de métricas fora de `send_once` no laço de entrega para que uma exceção não mate silenciosamente a thread.

Aceite: banco ocupado e liberado, erro de disco, receptor indisponível, reinício com lote pendente, resposta inválida e revogação. Nenhum evento já persistido deve ser apagado para “destravar”.

### A07 — P1: erro da atualização desaparece e diagnóstico pode parecer saudável

Locais: [agent_main.py:919](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/app/agent_main.py:919) e [agent_main.py:976](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/app/agent_main.py:976). Prova: `HIDDEN_POLL_ERROR`; diagnóstico verificado por leitura do fluxo.

`_command_failed("poll", ...)` libera a próxima consulta e retorna sem apresentar a falha. O exportador grava `self._health`, que é o último resultado recebido, com um horário de criação novo para o arquivo. Falhas repetidas podem deixar a interface e o JSON mostrando dados anteriores ao problema.

Resultado: a mensagem de erro sintética não é apresentada.

Correção: aviso persistente e discreto de atualização/captura falhando; manter `last_error`, horário da última amostra bem-sucedida e indicador de dados desatualizados. O diagnóstico deve distinguir hora da exportação de hora da coleta, incluir versão/build/backend e erros sanitizados. Não abrir diálogos repetidos a cada dois segundos nem salvar payloads/tickets.

Aceite: erro em uma consulta, erros repetidos e recuperação; o aviso aparece, os dados antigos são identificados e um diagnóstico novo não sugere leitura recente inexistente.

### A08 — P2: parar a captura descarta pacotes já aceitos sem contabilizar

Local: [live_stream.py:917](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/core/live_stream.py:917). Prova: `QUEUED_STOP_LOSS`.

O worker sai quando o sinal de parada é definido, mesmo com pacotes aceitos ainda na fila. Depois a fila é substituída sem contabilizar essa perda.

Resultado: **três pacotes aceitos, um processado, fila vazia e zero descartes informados**. Pode afetar os últimos eventos de EXP, recompensa, equipamento ou combate; não significa perda de eventos já confirmados na outbox.

Correção: primeiro encerrar a entrada, drenar o que foi aceito com prazo controlado e só depois concluir a sessão. Se o prazo não permitir drenagem, informar quantidade descartada e encerramento incompleto. Evitar também espera infinita em `WebAgentBridge.wait_until_idle()` quando o consumidor estiver morto ou preso.

Aceite: pausa/fechamento sob carga, callback lento, fila cheia e timeout; cada pacote deve ser processado ou contabilizado como não processado.

### A09 — P2: rede lenta bloqueia saúde, comandos e atualização

Locais: [windows_agent_capture.py:559](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/core/windows_agent_capture.py:559), sincronização de perfis/subsessões e `health`. Prova: `HEALTH_LOCK_DELAY`.

Chamadas de autorização/sincronização acontecem dentro do mesmo lock de `health`. O backend da interface é serial; uma consulta lenta também atrasa comandos posteriores. A API local usa `runtime.health`, portanto sua consulta de saúde participa desse bloqueio. A captura e a entrega possuem workers próprios: isso não prova que toda a janela ou toda a API congele.

Resultado: leitura de saúde fica esperando a autorização simulada; retorna quando ela é liberada. Há timeouts HTTP de até dezenas de segundos e mais de uma operação pode ocorrer no mesmo ciclo.

Correção: retirar I/O de rede do lock de estado e publicar snapshots curtos/coerentes. Preservar o bloqueio de autorização para iniciar captura quando necessário; não usar a melhoria de responsividade para contornar a licença/vinculação.

Aceite: autorização e sincronizações lentas/offline; consulta de saúde e mensagem de erro continuam disponíveis, não há fila ilimitada de consultas e nenhum comando usa estado inválido.

### A10 — P2: falha na criação do capturador deixa início parcial

Local: [windows_agent_capture.py:458](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/core/windows_agent_capture.py:458). Prova: `FACTORY_START_FAILURE`.

O worker do decoder e a sessão do serviço são iniciados antes de criar o capturador. Essa criação fica fora do bloco que desfaz um início malsucedido.

Resultado: falha de factory deixa **worker vivo e sessão do serviço ativa**, mas `runtime.session_id` continua vazio.

Correção: incluir todos os passos de aquisição no tratamento de falha e desfazer somente o que efetivamente começou, preservando o erro original. Aplicar o mesmo cuidado à criação do substituto/restauração em mudança de rota.

Aceite: erro em cada etapa do início, seguido de nova tentativa, sem worker/sessão órfã nem evento de ciclo de vida duplicado.

## Riscos adicionais: encontrados na leitura, não reproduzidos como incidente

| Área | Problema/limite encontrado | Correção ou validação necessária |
| --- | --- | --- |
| RAM e concorrência | Há limites reais de filas/fluxos/caches, mas a preferência de RAM é um orçamento adaptativo, não teto rígido de todo o processo. A compactação altera o decoder no caminho de saúde, enquanto o worker chama `decoder.feed` sem esse mesmo lock. | Serializar a compactação com o próprio worker ou proteção comum curta; testar frames partidos sob pressão. Medir Working Set, memória privada, handles e threads. Não prometer RAM fixa com base só no tamanho das filas. |
| Medição de memória | Os testes `test_stable_ten_hour_run_passes` e semelhantes analisam amostras sintéticas; não mantêm o Agent rodando dez horas. | Reutilizar `tools/memory_soak.py` no ensaio real, junto com progresso de captura/decoder/ACK. Um teste de analisador aprovado não homologa uma sessão longa. |
| Perdas ETW e liveness | Métricas herdadas de perdas ficam sem medição equivalente no fallback; faltam estatísticas nativas e saúde explícita de controlador/consumidor. Zero não prova ausência de perda. | Consultar estatísticas suportadas, registrar último pacote/evento e estado das threads/processo, mostrar “indisponível” quando não mensurado. Não reiniciar só porque o jogo está ocioso. |
| Custo do callback | Extração de Payload e tamanho faz consultas TDH/alocações por pacote antes de entrega ao decoder. | Medir CPU, taxa de entrada e perdas no Win10 real antes de otimizar; reaproveitar metadados/buffers apenas se a medição justificar. Não ampliar filtros para todo o tráfego como solução automática. |
| Logs | `logging.basicConfig(filename=...)` em `agent_main.py:1183` não define rotação. Uma falha repetida gera arquivo crescente. | Usar rotação nativa da biblioteca padrão e limite de arquivos, reduzir repetição de erros idênticos, manter evidência da primeira/última ocorrência. |
| Outbox cheia | Eventos persistidos são preservados; novas admissões podem falhar com `OutboxFullError`. O worker registra a exceção e conclui o item, sem replay genérico desse evento. Logo, fila limitada não significa armazenamento ilimitado sem perdas. | Política explícita de capacidade: alertar, limitar/pausar aquisição antes de esgotar quando possível, contabilizar eventos não persistidos. Nunca apagar os antigos automaticamente para esconder o acúmulo. |
| Instalação interrompida | `packaging/agent-installer.nsi:95` remove o diretório interno antigo antes de copiar a versão nova; sem recuperação transacional dessa etapa. | Validar espaço/locks previamente, preparar arquivos novos antes da troca e conservar rollback até conclusão. Testar interrupção, disco cheio e bloqueio de arquivo sem desativar antivírus. |
| Inicialização com Windows | A opção usa HKCU Run; o executável exige administrador. Essa combinação não foi validada em logon real de usuário padrão/administrador nesta auditoria. | Validar o fluxo real de consentimento. Não substituir por tarefa oculta/elevada ou serviço persistente sem decisão explícita. |
| Verificação de plataforma | O fallback verifica Windows x64 e existência de Pktmon, não uma matriz completa de build/capacidades do comando. | Pré-diagnóstico de versão/capacidades com mensagens claras. Alvo continua 22H2 x64; não ampliar a promessa para qualquer Win10/ARM/32 bits. |
| Reinício abrupto e disputa | Pktmon é um recurso compartilhado. Pré-checagem de estado não é uma prova atômica de propriedade; falha abrupta pode deixar estado que o próximo início considera ocupado. | Testar propriedade, controlador órfão e dois usuários/processos competindo. Recuperar somente recursos identificados como próprios; ambiguidades devem continuar bloqueadas. |
| Rede e suspensão | IPv4/TCP é o caminho tratado; mudança de adaptador, suspensão/retomada, offload, IPv6 e fragmentação não tiveram ensaio real aqui. | Validar o caminho usado pelo jogo e reconexões. ExitLag continua fora do suporte solicitado neste ciclo; não atribuir falhas a ele sem evidência. |

Para perdas ETW, a fonte adequada são campos de [EVENT_TRACE_PROPERTIES consultados com ControlTrace](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/ns-evntrace-event_trace_properties). **Não usar `EVENT_TRACE_LOGFILEW.EventsLost` como correção:** a própria [documentação dessa estrutura](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/ns-evntrace-event_trace_logfilew) o marca como não utilizado.

## Controles existentes que precisam ser preservados

- Fallback por capacidade da DLL, sem instalar driver de captura alternativo ou invadir o processo do jogo.
- Estado Pktmon ocupado/desconhecido falha de forma segura; a correção de texto da beta.45 permanece necessária.
- Fluxos TCP distintos para conexões diferentes e identidade por processo com proteção contra reutilização de PID, cobertos pelos testes existentes.
- Filas e caches limitados; API local autenticada e em loopback. Melhorar liveness não deve expor essa API na rede sem autorização.
- Outbox SQLite com WAL, `synchronous=FULL`, sequência persistente e lote em trânsito preservado; confirmação do receptor antes da retirada normal de eventos.
- Separação das políticas de dados pessoais confirmados, eventos locais e observações de Boss exportáveis. Não alterar semântica de combate/recompensa para compensar perda de transporte.
- Atualização com manifesto/procedência Ed25519, verificação de hash e consentimento para instalação. Authenticode continua fora do projeto por decisão do proprietário; não introduzir bypass de antivírus.

## Ordem de correção e gates

1. **Continuidade dos dados:** A01/A02 no remontador TCP e A03/A05/A10 no ciclo de vida. Transformar as respectivas provas em testes de comportamento correto, preservando um e múltiplos clientes.
2. **Rotas e recuperação:** A04 e A06; manter limites, propriedade do Pktmon, lote e sessão. Incluir falhas intermitentes, não apenas início feliz.
3. **Visibilidade e encerramento:** A07/A08/A09, perdas ETW, logs e compactação concorrente. Sem “capturando” falso ou descartes invisíveis.
4. **Regressão e pacote:** suíte completa, replay, validação dos módulos realmente empacotados e instalador isolado. Publicação é um gate separado, não parte desta auditoria.
5. **Homologação no Windows 10 afetado:** aprovação somente com evidência do ambiente real e dos fluxos abaixo.

| Cenário real ainda pendente | Critério de aceite |
| --- | --- |
| Iniciar/pausar/continuar/fechar com um e dois ou mais clientes | Estado e duração por cliente corretos; sem mistura de identidade, duplicação de sessão ou recursos órfãos |
| Trocas de mapa/conexão e abrir/fechar apenas um cliente | Outros clientes continuam decodando; filtros limitados; conexões novas funcionam sem relogar todos |
| Farm, equipamentos/inventário, ranking e mercado | Eventos esperados chegam à outbox e são confirmados pelo receptor; distinguir captura, projeção, envio e processamento no site |
| Boss e PvP pela API local | Informações progridem e expiram corretamente; lentidão do site não deve mascarar a saúde local |
| Site offline, autorização lenta, banco temporariamente ocupado | Captura respeita autorização; erro visível; entrega recupera sem apagar fila nem duplicar o lote |
| Falha de captura, suspensão e retomada | Recuperação somente dos recursos próprios, sem estado ativo falso |
| Sessão longa no uso normal do usuário | Taxas continuam avançando; amostras de RAM, CPU, handles, threads, filtros, perdas e ACK permitem avaliar estabilidade, não apenas um pico isolado |
| Atualizar/reiniciar após fechamento abrupto | Identidade e fila preservadas, instalador recuperável e nenhum controlador próprio abandonado |

Para fechar a causa do incidente remoto, coletar durante a falha: versão instalada, horário, se a janela responde, quais contadores pararam, diagnóstico do Agent e o log `%LOCALAPPDATA%\Karvalho\RF QOL Agent\logs\rf-qol-agent.log`. O diagnóstico atual pode estar desatualizado (A07), portanto deve ser confrontado com o log e a observação do momento. Não enviar tokens, tickets, payload de sessão ou chaves de pareamento.

## Reproduzir esta auditoria

Script: [audit_windows10_beta45.py](K:/MCP/_release-builds/rf-qol-agent-2.0.0-beta.45/rf-next-info/tools/audit_windows10_beta45.py).

Na raiz `rf-next-info`, com o ambiente Python do projeto:

```powershell
python -m tools.audit_windows10_beta45
python -m unittest tests.test_pktmon_etw tests.test_windows_agent_capture -q
python -m unittest discover -s tests -q
```

O script usa pacotes sintéticos, estado temporário e mocks das chamadas nativas. Não envia dados ao site, não executa comandos Pktmon e não controla a interface. `reproduced: true` significa **defeito observado**. O assert final verifica o baseline vulnerável da beta.45; depois das correções esse script deve ser convertido/atualizado, e não usado para exigir que os bugs continuem existindo.

O replay privado só é incluído na regressão quando `RFQOL_EQUIPMENT_PCAP` aponta para a captura autorizada disponível. Nenhum payload foi adicionado aos arquivos desta auditoria.

## Entrega, reversão e próximo passo

A rotina `operar-mcp` foi usada para separar evidências, propostas e gates de publicação. Não houve commit remoto, PR, release ou mudança no servidor. Não é necessário rollback do produto: somente relatório/script locais foram acrescentados. Custo real de execução: desconhecido.

Próximo passo recomendado: implementar o primeiro grupo de correções com testes de comportamento correto e seguir pelos demais grupos, sem declarar o incidente físico resolvido antes da homologação no Windows 10 afetado.
