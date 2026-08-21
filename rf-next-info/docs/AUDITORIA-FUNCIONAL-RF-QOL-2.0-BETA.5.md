# Auditoria funcional — RF QOL 2.0.0-beta.5

Data: 21/08/2026

## Objetivo

Validar a correção do chefe que permanecia na tela após sair da proximidade e
revisar o comportamento do RF QOL com múltiplos clientes e múltiplas sessões.
Esta auditoria separa testes automáticos, repetição de capturas reais e ensaios
que ainda dependem do executável instalado e do jogo.

## Correção da vida do chefe

Causa confirmada: o evento `disappear_unit_list` removia monstros comuns, mas
mantinha a âncora visual de Boss por até seis horas para preservar o acumulado
de dano. A mesma estrutura estava sendo usada para duas responsabilidades
diferentes: proximidade/vida visível e total do encontro.

Correção aplicada:

- a presença visual e a vida do Boss são removidas imediatamente quando o UID
  sai da proximidade;
- o total de dano permanece em uma estrutura separada e pode continuar se o
  mesmo UID reaparecer durante o encontro;
- se a morte chegar depois do desaparecimento, o acumulado desse encontro
  também é encerrado;
- o desaparecimento de um Boss em um cliente não afeta outro cliente;
- uma nova sessão começa sem Boss, PvP, mapa ou combate efêmero da sessão
  anterior;
- os overlays de vida e DPS voltam ao estado “Aguardando boss próximo”.

## Resultado automático

Comando de regressão: `python -m unittest discover -s tests -p "test_*.py"`

Resultado final: **412 testes executados e 412 aprovados em 96,469 segundos**.

| Área | Resultado | Evidência principal |
| --- | --- | --- |
| Captura e recuperação | Aprovado | início, pausa, continuação, encerramento, rotação e fallback |
| Roteamento de clientes | Aprovado | identidade canônica, ExitLag, eventos sem dono e isolamento por cliente |
| Múltiplos clientes | Aprovado | atividade de Farm isolada para sete clientes e Boss isolado para dois |
| Múltiplas sessões | Aprovado | três sessões sequenciais e leitura exclusiva da sessão mais recente |
| Subsessões | Aprovado | início manual/automático, encerramentos e persistência sem mistura |
| Status | Aprovado | Teleportando, PvP, Farm e Ocioso com prioridade e expiração |
| PvE | Aprovado | dano, abate, alvo, vida própria e atividade de Farm |
| PvP | Aprovado | alvo atual, dano real, expiração de aparições e isolamento ExitLag |
| Boss | Aprovado | vida, dano acumulado, guildas, desaparecimento, reaparecimento e morte |
| Drops e chat | Aprovado | evento de recompensa, outros jogadores, deduplicação, filtros e raridade |
| Alertas | Aprovado | sons, categorias múltiplas, raridades e controle de repetição |
| Mapas | Aprovado no contrato | posição relativa, foco, zoom, regiões, fallback manual e limite de clientes |
| Ranking de EXP | Aprovado | histórico, deduplicação horária, cálculo, envio e CSV |
| Inventário e bancos | Aprovado | isolamento, limites de linhas/ícones e payloads sanitizados |
| API local e LAN | Aprovado | saúde, sessões, mapa, status, autenticação e limites de resposta |
| Licença e atualização | Aprovado | lease v3, janela offline, módulos, rollback assinado e versão monotônica |
| Memória | Aprovado em testes acelerados | filas, históricos, ícones, pressão e compactação possuem limites |
| Interface Qt | Aprovado automaticamente | renderização, overlays, filtros, tabelas e ações principais |
| Empacotamento | Aguardando etapa de release | perfil beta, build e instalação limpa serão validados após o commit |

Distribuição dos testes:

- núcleo e decoders: 148;
- interface principal e persistência: 97;
- interface Qt: 90;
- operações Qt e captura: 45;
- dados Qt: 6;
- API local: 6;
- estabilidade de memória: 5;
- caminhos e armazenamento: 5;
- licença v3: 4;
- perfil de build: 4;
- alertas de som: 2.

## Repetição com capturas existentes

Foram repetidas as capturas locais mais recentes sem alterar dados do usuário:

- 50 arquivos produziram 152.917 eventos decodificados, distribuídos entre
  dois clientes;
- ambos os clientes tiveram identidade local reconhecida e atividade PvE/Farm
  atribuída ao cliente correto;
- os drops permaneceram separados por cliente;
- dois Boss reais (`Corruptor de Mecha` e `Orkus`) apresentaram evento de
  aparecimento seguido de desaparecimento, sem morte no trecho capturado;
- ao repetir 147.002 eventos pelo fluxo de monitoramento corrigido, o estado
  final teve zero âncoras de Boss e nenhuma vida de Boss visível;
- não foi encontrado payload sensível `0x0101` nesse conjunto.

## Estresse de sessões e clientes

Foi criada uma base temporária com 20 sessões sequenciais e sete clientes em
cada sessão. A última leitura retornou somente os sete clientes, drops e UIDs
da sessão 20, sem interseção com a sessão 1. A base temporária foi descartada
após a verificação.

## Limites desta auditoria

Os itens abaixo não são declarados como validados em uso real:

- ensaio visual/manual do executável durante uma luta completa de Boss;
- captura PktMon ao vivo neste processo sem elevação: o Windows retornou
  `0x80070005`, e o fallback previsto foi validado automaticamente;
- teste contínuo de 10 a 14 horas do executável instalado e medição do pico de
  RAM; os limites foram verificados por testes acelerados, não por duração real;
- envio real para o site e efeitos externos, pois a auditoria não publicou
  dados de teste;
- reconhecimento automático de mapa quando a captura começa depois da entrada
  no mapa e não contém o evento de mapa/teleporte. Nesse caso, a posição pode
  existir sem índice de mapa e o fallback manual deve ser usado;
- validação manual de arrastar, redimensionar e autofit de todas as tabelas.

Esses pontos são gates de ensaio do instalador, não falhas ocultadas como
aprovação automática.
