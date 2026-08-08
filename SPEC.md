# SPEC — RF NEXT QOL

## Escopo aprovado

- Windows 10/11 x64; grupo fechado; até 25 computadores no primeiro ano.
- Pktmon nativo; sessão manual e contínua; bandeja com escolha na primeira execução.
- Informações atualizadas durante a captura em intervalo configurável, com
  padrão de 30 segundos; EXP e Loot permanecem uma sessão lógica contínua.
- Monitor PvE mostra o último monstro confirmado por dano, vida atual/máxima
  e idade do estado; Monitor PvP mostra o último jogador confirmado em
  combate, vida atual/máxima e DPS de dano em HP numa janela de 10 segundos.
- O Monitor PvE também lista, por cliente, bosses próximos confirmados pelas
  marcações oficiais do catálogo, mesmo sem ataque do personagem local.
- Monitor PvE, Monitor PvP e Boss podem ser ligados independentemente da
  captura histórica. Sem captura histórica, os pacotes são processados em RAM
  e descartados após atualizar o estado; nenhum PCAP ou ETL é preservado.
- PvE e PvP possuem intervalos de atualização independentes. O capturador
  nativo é único e distribui snapshots e deltas aos monitores sem reiniciar o
  Pktmon.
- Monitor PvE lista um cartão por tipo de mob visível, além do alvo atual, com
  imagem, nome, level e HP atual bruto confirmado; o cartão não substitui o
  valor bruto por percentual.
- Na próxima versão, os cartões dos monitores usam altura mínima compatível
  com a fonte, margens internas e espaçamento vertical suficientes; textos e
  valores não podem ficar cortados ou sobrepostos, e a rolagem preserva o
  espaço entre cartões quando a lista ultrapassar a janela.
- Em janela, os monitores exibem os Clientes A e B em linhas separadas; quando
  maximizado ou em tela cheia, dividem a área igualmente em duas colunas, como
  na Visão geral.
- Monitor PvP lista jogadores visíveis com nome, level, classe confirmada e
  guilda; relações não confirmadas nunca recebem o rótulo de inimigo.
- Na próxima versão, a leitura PvP não mantém cartões de jogadores sem
  confirmação recente e remove estados expirados; jogadores realmente
  confirmados nas proximidades devem aparecer mesmo sem serem o alvo atual.
- A página Boss exibe imagem, HP atual/máximo, DPS global por perda de HP, dano
  observado, ETA e rankings por jogador e guilda. Ranking por party/raid só é
  exibido após a composição ser confirmada pelo protocolo.
- Alertas locais configuráveis por Profile: personagem/guilda próximos, dano
  PvP recebido, HP abaixo do limite e boss detectado; cada regra possui som,
  visual e cooldown.
- Atalhos globais dos monitores e overlays não podem ativar nem trazer a janela
  principal para frente.
- Na próxima versão, atalhos globais separados e configuráveis ligam e desligam
  os monitores PvE e PvP, inclusive com o programa em segundo plano.
- Na próxima versão, os overlays usam fundo transparente, preservando somente
  os elementos visuais e informações do monitor.
- `0x031D FG2C_notify_boss_result_Message` é a fonte primária planejada para
  recompensa de boss e recebedor. O layout precisa fechar exatamente e passar
  por captura marcada antes da persistência; `0x040A` é confirmação local.
- O catálogo persistente de mobs contém somente Nome, Level, HP máximo e
  Localização. `npc_index` e versão são chaves técnicas internas de dedupe.
- Identidade persistente usa servidor/mundo + `character_uid`; participação em
  guilda é temporal. O upload ao Dev é sanitizado, consentido e idempotente.
- Snapshot completo de mercado é enviado automaticamente quando `is_end=true`
  para o mesmo `exchange_server_type`, sem abrir janelas ou agir no jogo.
- Entrada do personagem, Mercado, Codex e Memory Chips usam janelas marcadas
  de 10 segundos com atalhos próprios, sem iniciar outro Pktmon.
- Atalhos configuráveis. Capturas, leituras e exportações usam uma pasta
  escolhida dentro do aplicativo; caminho inválido gera erro e nunca cai
  silenciosamente em `%AppData%`.
- Na próxima versão, a barra superior exibe o consumo atual de memória RAM do
  próprio RF NEXT QOL, em MiB, atualizado durante a execução.
- Personagem, level, EXP, Mercado, Codex, farm e kills estimadas por recompensa.
- Um Profile com até dois personagens simultâneos, separados por UID confirmado.
- PID, porta e ordem do processo nunca são identidade definitiva de personagem;
  sem UID confirmado, o cliente recebe apenas um nome manual temporário.
- A beta mantém um histórico local dos UIDs confirmados por `0x0106` e permite
  escolher `Automático` ou um personagem conhecido separadamente para os
  Clientes A e B. O mesmo UID não pode ocupar os dois clientes e uma identidade
  canônica posterior substitui e corrige o vínculo manual divergente.
- O histórico do UID também preserva a última classe
  confirmada pelo Biosuit e o último Rover confirmado do próprio personagem.
  Ao selecionar um UID antigo, esses dados aparecem como estado histórico até
  uma captura atual confirmá-los ou substituí-los; Rover de personagens
  próximos nunca pode atualizar esse histórico.
- Cada parada cria uma sessão; JSON/CSV são separados por personagem e sessão.
- EXP/Loot permite subsessões manuais ou automáticas por personagem, com
  localização, mobs em multiseleção, nível por mob e opção Outro.
- Na próxima versão, a criação de novas subsessões terá filtro de level para
  reduzir as opções de mobs exibidas. O formato do filtro (valor, faixa ou
  multiseleção) será fechado na proposta visual antes do código, sem alterar
  ou perder seleções já feitas.
- Na próxima versão, as configurações de subsessão terão opção de favoritos.
  Cada favorito representa a configuração completa da subsessão, formada pela
  soma de todas as opções configuradas, e não um mob, mapa ou spot isolado.
- Na próxima versão, o envio de subsessões deve usar exatamente o contrato
  aceito pelo site, com os mesmos campos, tipos e identificador idempotente.
  A correção só é considerada concluída após uma subsessão selecionada ser
  recebida e consultável no site sem duplicação; rejeições da API ficam
  visíveis no programa e registradas no log.
- JSON completo + CSV resumido; SQLite transacional para recuperação.
- Arquivos brutos segmentados sem descarte automático.
- Na próxima versão, um botão `Encerrar sem ler` interrompe a captura sem
  iniciar a leitura ou a decodificação; os arquivos brutos permanecem salvos
  para leitura posterior ou descarte manual.
- Alertas: 5 GB; 10 GB ou 10% livre; encerramento seguro abaixo de 2 GB livres.
- Após exportar: mostrar tamanhos, validar o arquivo e oferecer envio dos brutos à Lixeira.
- Licença online a cada 24h, tolerância de 72h; depois bloquear novas capturas e preservar exportação.
- A exportação e a recuperação dos arquivos existentes permanecem disponíveis sem licença reconhecida.
- Captura PktMon pendente após falha deve ser recuperável sem apagar o ETL.
- Atualização GitHub stable/beta, visível e confirmada, com manifesto assinado, SHA-256 e rollback de uma versão.
- Sem telemetria; diagnósticos e logs sanitizados só são enviados após consentimento.
- Log técnico local rotativo de até aproximadamente 4 MB; envio, pasta e cópia manual na aba Licença.
- Envio ao site usa API HTTPS idempotente e token revogável por Profile; o
  programa nunca recebe credenciais do banco. O servidor armazena somente o
  hash do token, e o Windows protege a cópia local.
- Interface profissional baseada no kit RF Next da identidade Karvalho. A logo
  oficial é copiada dos assets da marca; mockups gerados não são fonte de logo.
- Instalador, dependências, capturador, banco, configurações, logs, cache e
  atualizador permanecem na pasta selecionada durante a instalação. Novas
  instalações não usam `%AppData%`, `%LocalAppData%` nem `%ProgramData%`.
- Atualizações reutilizam a pasta instalada. Dados legados só são removidos
  depois de copiados e validados; o desinstalador permite preservar os dados.

## Marca

Fonte oficial: `K:\Karvalho\Identidade Visual Karvalho`.
Nome do produto: `RF NEXT QOL`.

## Gates

- Pktmon precisa ser comparado com captura real conhecida.
- Antes da atualização periódica, testar se um segmento multi-file fechado é
  legível durante a captura e medir a lacuna real de qualquer stop/start.
- Uma captura segmentada deve preservar frames TCP partidos entre segmentos e
  produzir os mesmos eventos da captura contínua de controle.
- Streaming em RAM deve manter latência captura-tela p95 abaixo de 500 ms,
  ressincronizar a UI em menos de 1 segundo e não crescer continuamente em
  teste de 12 horas.
- Scanner de segurança deve confirmar ausência de token, ticket e payload
  `0x0101` em arquivos, banco, IPC e logs.
- Reenvio da mesma sessão/lote ao site não pode criar registros duplicados.
- O layout de `0x031D` deve ser revalidado na versão corrente, reconciliado com
  a recompensa observada e coberto por golden frame antes de produção.
- Instalação, primeira execução e atualização não podem criar arquivos do
  produto nas pastas de AppData/ProgramData.
- Piloto sem assinatura não é release pública.
- Publicação no GitHub somente após testes e revisão.

## Limites confirmados desta implementação

- O programa somente chama um jogador de hostil quando o protocolo permite
  comparar o `realm` dele com o do personagem local. Sem essa confirmação, o
  cartão permanece como não classificado.
- Guilda, grupo e raid só entram em contagens/rankings quando seus
  identificadores forem recebidos explicitamente no evento decodificado.
- Os cartões procuram retratos em `assets/mob-icons/<npc_index>.*`. A versão
  1.28.5 analisada não contém um catálogo validado desses retratos; nenhum
  ícone de item é reutilizado como se fosse imagem de mob.
- `0x031D` está catalogado, mas seu layout de recompensa/recebedor ainda não
  foi fechado. A tabela do site está preparada, porém o histórico fica
  desativado até uma captura marcada permitir um decoder verificável.
