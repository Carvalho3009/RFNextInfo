# Changelog

## 2.0.0-beta.40 — 2026-09-06

- vincula conexões à instância do cliente (PID e horário de criação), mantendo
  a identidade confirmada durante intervalos sem conexão TCP;
- remove da tela somente o cliente cujo processo encerrou ou foi substituído,
  sem apagar outros personagens pela contagem de conexões;
- reinicia o reagrupamento TCP quando uma porta é reutilizada por outra instância;
- correlaciona equipamentos equipados usando a aparição do próprio personagem
  e o perfil, aceitando somente correlações completas para envio ao site;
- mantém a proteção contra UID conflitante; PID não confirma personagem sozinho.
- corrige uma disputa entre pausa e retomada rápida que podia registrar a sessão
  retomada como uma captura nova.

## 2.0.0-beta.39 — 2026-09-06

- mantém o nome e o nível do personagem na tela quando chegam atualizações
  parciais de equipamento, Rover, biosuit ou poder para o mesmo UID;
- não reaproveita esses dados quando o UID realmente muda.

## 2.0.0-beta.38 — 2026-09-03

- exibe na tela do Companion a identidade estável de cada Agent;
- mantém o identificador completo disponível sem expor credenciais.

## 2.0.0-beta.37 — 2026-09-02

- envia ao site as listas completas top 100 de contribuição de Accretia,
  Bellato e Cora;
- mantém UIDs e campos internos do ranking somente no Agent.

## 2.0.0-beta.36 — 2026-09-02

- recupera o snapshot de equipamentos quando o Windows ainda não associou as
  conexões TCP do mesmo cliente, usando os UIDs exatos dos itens;
- mantém isoladas as rotas já identificadas como clientes diferentes.

## 2.0.0-beta.35 — 2026-09-02

- distingue corretamente os rankings de contribuição das facções Accretia,
  Bellato e Cora, preservando os identificadores brutos recebidos do servidor;
- separa lista completa e posição própria nas respostas de ranking de facção.

## 2.0.0-beta.34 — 2026-09-02

- atualiza o Agent com os decodes confirmados de Power na rota TCP 12040,
  MAU/Launcher, ranking de contribuição e avisos de itens do sistema;
- preserva os filtros existentes de loot, alvos e combate e mantém mensagens
  de aprimoramento ou primagem fora do histórico de drops.

## 2.0.0-beta.33 — 2026-09-02

- correlaciona aparências de equipamento entre rotas TCP do mesmo cliente
  lógico, preservando a separação entre clientes e permitindo ao site marcar
  corretamente os itens equipados no Inventário.

## 2.0.0-beta.32 — 2026-08-31

- envia ao site fotografias consolidadas de encontros de Boss pela fila
  assinada do Agent, com prioridade imediata, deduplicação e limite de uma
  atualização por segundo por encontro;
- inclui Chefe, HP e dano total por personagem, com UID público e guilda
  quando disponíveis, sem enviar golpes brutos, referências locais ou PvP;
- preserva a API local de Boss para monitores externos.

## 2.0.0-beta.31 — 2026-08-31

- melhora a fotografia de Inventário, evitando classificar como empilháveis os
  equipamentos do tipo 27 e preservando a correlação de aparência e loadout;
- amplia Coleção/Códex com tipo e slots concluídos ou ausentes, sem enviar
  identidade de sessão ou misturar personagens e instalações;
- mantém a fotografia pendente para nova tentativa quando a fila offline falha
  durante a gravação, em vez de perder silenciosamente parte do snapshot.

## 2.0.0-beta.30 — 2026-08-30

- resolve a identidade da rota TCP já no primeiro pacote, antes de fixar o fluxo
  lógico, inclusive quando a conexão surge entre duas verificações periódicas;
- impede que subsessões continuem apenas com o cronômetro enquanto EXP,
  contribuição, créditos e kills passam a usar outra referência de cliente.
- envia a lista completa de anúncios pessoais como fotografia autoritativa,
  inclusive quando não existe anúncio ativo;
- permite ao Companion encerrar anúncios vendidos, removidos ou republicados
  que deixaram de aparecer na lista atual, sem apagar o histórico.
- reconhece mensagens explícitas de estado, HP, contribuição e resultado de
  World Boss na prioridade local do Monitor de Boss.

## 2.0.0-beta.29 — 2026-08-29

- dá prioridade máxima no processamento local aos eventos explícitos de Boss,
  ao combate classificado como Boss e ao contexto necessário de aparição e
  desaparecimento, sem liberar esses eventos para envio ao site;
- inclui `world.players_appeared` no domínio local de Boss e associa cada
  personagem do encontro a `guild_id` e `guild_name`, mantendo `guild` como
  alias compatível;
- preserva a separação por cliente e sessão, evita duplicação durante a
  confirmação de identidade e mantém o processamento normal e os ciclos da
  sessão sem regressão.

## 2.0.0-beta.28 — 2026-08-29

- preserva no envio automático do Mercado as linhas em que o jogo informa
  `highest_price = 0`, usando o menor preço válido como limite superior, como a
  exportação manual já fazia;
- evita que itens válidos desapareçam antes de chegar ao site, incluindo o caso
  observado de `Pioneer's Erebus Blade +5`;
- adiciona regressão específica para item épico refinado e mantém o contrato do
  site inalterado.

## 2.0.0-beta.27 — 2026-08-29

- adiciona a rota local autenticada `GET /api/agent/v1/boss/encounters` para o
  Monitor de Boss e o painel do Discord;
- consolida por encontro o nome e o HP do Boss, além do nome, UID permanente,
  guilda e dano total acumulado de cada personagem;
- mantém encontros separados por cliente, ignora eventos duplicados antes da
  soma e remove o Boss somente por desaparecimento, morte, resultado confirmado
  ou encerramento da sessão;
- anuncia o novo contrato em `capabilities`, preservando o feed genérico para
  compatibilidade com versões anteriores do Monitor de Boss.

## 2.0.0-beta.26 — 2026-08-28

- exige UID público, nome de personagem e resposta válida antes de confirmar a
  identidade inicial de uma conexão;
- impede que outro UID direto substitua o personagem já confirmado na mesma
  conexão, sem bloquear uma confirmação direta que corrija recuperação histórica;
- mantém atualizações parciais de equipamento e Power somente para o UID já
  confirmado e expõe contadores para eventos diretos inválidos ou conflitantes;
- envia ao site cada mapa confirmado pelo retorno bem-sucedido do teleporte,
  com o horário UTC do pacote, referência do mapa anterior e deduplicação por
  cliente; posição e repetição do mesmo mapa não criam novas trocas;
- separa snapshots de equipamentos e itens empilháveis sem descartar uma das
  categorias no site, recompõe o inventário completo após cada delta e evita
  reenfileirar estados idênticos;
- aceita a remoção do último item de uma categoria, isola o estado por cliente
  e atualiza o loadout por UID exato após trocas de slot confirmadas;
- publica o perfil de equipamentos somente quando o UID correlacionado pertence
  ao personagem confirmado da conexão, bloqueando contaminação por jogadores
  próximos.

## 2.0.0-beta.25 — 2026-08-28

- elimina observações idênticas e repetidas de personagem/power antes que elas
  ocupem a fila offline;
- mantém eventos imediatos à frente, mas limita rajadas consecutivas para que
  Mercado, Ranking, eventos em tempo real e dados de volume continuem sendo
  drenados mesmo quando há atualizações imediatas contínuas;
- preserva os eventos pendentes e o ACK idempotente; a correção não exige
  alteração do contrato do servidor.

## 2.0.0-beta.24 — 2026-08-27

- impede que atualizações de equipamento de jogadores próximos sejam tratadas
  como identidade do personagem local;
- mantém o personagem confirmado vinculado à sessão e ignora perfis remotos
  sem nome confirmado, evitando abas e sessões falsas no site;
- preserva a separação entre clientes e permite que o servidor repare, de
  forma não ambígua, sessões legadas vinculadas a UIDs sem nome.

## 2.0.0-beta.23 — 2026-08-27

- adota o nome RF Next Companion e o logo do Companion na janela, bandeja,
  executável e instalador, preservando o diretório de dados e a instalação
  anterior durante a atualização;
- reduz falsos personagens reconhecidos ao remover conexões antigas quando as
  rotas de captura mudam;
- envia kills PvE somente depois da confirmação do personagem e mantém a
  atribuição separada por cliente;
- correlaciona o UID do equipamento ativo com o inventário, marcando como
  equipados somente os itens que realmente compõem o loadout;
- mantém drops próprios e anúncios públicos em contratos separados, sem enviar
  aprimoramentos ou primagens como loot;
- sincroniza sessões e subsessões remotas sem misturar clientes e preserva a
  fila local até a confirmação do servidor.

## 2.0.0-beta.22 — 2026-08-26

- adiciona instalador NSIS próprio do Agent, com atualização sobre a instalação
  existente e preservação do estado em `LocalAppData`;
- adiciona canal beta de atualização automática com manifesto Ed25519, origem
  HTTPS restrita, tamanho e SHA-256 obrigatórios e escrita atômica;
- mantém a aplicação visível e condicionada à confirmação do usuário antes de
  encerrar a captura, reiniciar e abrir o instalador;
- registra a decisão de não usar Authenticode, sem criar exceções no Defender,
  executar scripts remotos, usar UPX ou trocar silenciosamente o executável;
- gera chave Ed25519 exclusiva do Agent, protegida por DPAPI fora do pacote.

## 2.0.0-beta.21 — 2026-08-26

- Mostra na janela as taxas reais por segundo de eventos gerados, enviados e
  de crescimento ou redução da fila offline.
- Mantém golpes, skills e alterações de HP/FP somente na API local e remove da
  fila legada esses eventos sem consumidor no site; kills PvE, EXP,
  contribuição, drops, Mercado e Ranking continuam remotos.
- Expõe também o fluxo do último minuto na saúde sanitizada da API local.
- Amplia para 20 segundos a espera por lotes grandes já aceitos pelo receptor,
  evitando retentativas prematuras que reduziam a vazão da fila.

## 2.0.0-beta.20 — 2026-08-26

- Adiciona entrega durável por prioridade: eventos imediatos primeiro, Mercado
  e Ranking de EXP em prioridade alta, eventos em tempo real e, por último,
  dados de volume.
- Acelera a drenagem da fila com acionamento após cada evento e rajadas de até
  oito lotes, mantendo o limite seguro de 250 eventos ou 224 KiB por lote.
- Preserva retries idênticos e ACK parcial ao enviar sequências não contíguas;
  a migração da outbox existente é aditiva e não remove eventos pendentes.
- Expõe volume enfileirado/enviado no último minuto, crescimento da fila,
  contagem por prioridade e métricas das rajadas no diagnóstico local.
- Mostra na lista de personagens a duração da sessão atual de cada cliente,
  iniciada no reconhecimento individual e sem reiniciar os demais clientes.

## 2.0.0-beta.19 — 2026-08-26

- Inclui a curva de EXP no pacote independente do Agent, permitindo projetar e
  enviar ao site as posições decodificadas do ranking sem exigir rolagem.
- Faz o autoteste do executável falhar quando a curva de EXP obrigatória não
  estiver disponível, evitando distribuir novamente um pacote incompleto.

## 2.0.0-beta.18 — 2026-08-26

- Recupera automaticamente somente o fluxo TCP que permaneceu bloqueado por um
  segmento ausente, sem reiniciar a captura, os demais clientes, a sessão ou a
  fila offline.
- Expõe contadores sanitizados de fluxos bloqueados/recuperados e o horário do
  último evento decodificado na saúde local do Agent.
- Corrige a leitura do worker de entrega na API local e mostra na janela o
  último decode e a última confirmação de lote recebida do servidor.

## 2.0.0-beta.17 — 2026-08-25

- Só envia ao site dados privados e ações do personagem depois que um UID
  público válido confirmou o vínculo daquela conexão.
- Mantém eventos ainda não confirmados disponíveis aos monitores pela API local,
  sem colocá-los na fila offline nem misturar clientes.
- Limita o heartbeat remoto e usa identificadores únicos após reinício, evitando
  que uma confirmação repetida deixe o último evento preso na fila.

## 2.0.0-beta.16 — 2026-08-25

- Corrige o acúmulo da fila offline causado por envelopes que ultrapassavam por
  poucos KiB o limite descompactado do receptor.
- Reduz o tamanho-alvo dos lotes futuros, reservando espaço para o envelope, e
  trata o limite antigo do servidor como recuperável sem apagar eventos.

## 2.0.0-beta.15 — 2026-08-25

- Retoma automaticamente a entrega depois que um receptor antigo recusou uma
  sobreposição recuperável de lote, sem apagar ou remontar a fila offline.
- Expõe na API local somente o estado sanitizado do worker de entrega, incluindo
  backoff, último código de erro e contadores, sem credenciais ou conteúdo.

## 2.0.0-beta.14 — 2026-08-24

- Torna o reenvio da fila offline estável entre tentativas e reinicializações,
  com recuperação segura quando o servidor já recebeu parte do lote.
- Separa identidades e sessões por conexão para impedir mistura entre dois ou
  mais clientes, inclusive antes de o personagem ser reconhecido.
- Mantém Boss e PvP somente na API local; envia ao site apenas combate PvE
  confirmado, com atribuição de kill ao próprio cliente.
- Atualiza o decode dos eventos atuais de Boss e dos anúncios de loot com
  múltiplos registros, ignorando mensagens de aprimoramento e primagem.
- Envia Mercado em blocos sem truncar snapshots, além de inventário, coleção,
  Rover e heartbeat sanitizados.
- Filtra EXP, contribuição e moedas reservadas do histórico de drops; consolida
  anúncios públicos iguais vistos simultaneamente por clientes diferentes.
- Preserva eventos de EXP até o vínculo tardio do personagem e adiciona staging
  durável para observações de mapa e proximidade.
- Evita reiniciar a captura por desaparecimento transitório de rotas do jogo.

## 2.0.0-beta.13 — 2026-08-24

- Corrige o vínculo que permanecia pendente no Agent depois de o usuário
  confirmar o código no site. Enquanto aguarda vínculo, o Agent consulta o
  servidor novamente em até 5 segundos; depois de autorizado, volta ao
  intervalo normal de 30 minutos.

## 2.0.0-beta.12 — 2026-08-24

- Corrige as cores do menu da bandeja, incluindo itens normais, selecionados,
  desativados e separadores, preservando a leitura no tema escuro.
- Mostra o consumo real de RAM junto ao limite configurado e reduz estado
  efêmero quando o processo atinge o teto, sem descartar a outbox persistida.
- Adiciona vínculo do Agent à conta do site por código curto. O nome do usuário
  vinculado aparece no Agent e novas capturas exigem autorização válida.
- Revalida a autorização ao abrir e periodicamente; a cópia local protegida por
  DPAPI vale no máximo 24 horas e é invalidada na primeira resposta de revogação.
- Mantém Boss, PvP e combate exclusivamente na API local, sem incluí-los no
  contrato remoto de autorização ou na outbox do site.

## 2.0.0-beta.11 — 2026-08-24

- Mantém eventos de combate, PvP e Boss exclusivamente na API local usada
  pelos programas de monitoramento separados; esses eventos não entram na
  outbox e nunca são enviados ao site.
- Coloca em quarentena eventos locais que tenham ficado pendentes na outbox de
  versões anteriores, registrando somente o identificador e o motivo da
  remoção, sem preservar ou transmitir o conteúdo.

## 2.0.0-beta.10 — 2026-08-24

- Envia ao receptor dedicado os eventos sanitizados já confirmados de sessão,
  personagem, level/EXP, contribuição, recompensas, combate, PvP, Boss, mapa e
  proximidade, sem pacotes brutos, credenciais ou UID de sessão.
- Publica observações de Mercado e apenas snapshots completos e consistentes do
  Ranking EXP Top 100; páginas parciais e duplicadas ficam locais.
- Mantém a identidade confirmada ao pausar e continuar a captura na mesma
  conexão, mas a remove ao encerrar para impedir atribuição indevida.
- Limita posições contínuas a uma atualização por segundo, preservando todos os
  eventos de teleporte e reduzindo o volume que ocultava dados úteis.
- Adiciona diagnóstico limitado por tipo para separar eventos decodificados,
  aceitos, projetados, ignorados e rejeitados sem expor o conteúdo capturado.

## 2.0.0-beta.6 — 2026-08-21

- Corrige os travamentos causados pela abertura do banco de captura em modo de
  escrita a cada 250 ms durante a verificação de subsessões. O banco só é
  aberto quando uma condição de encerramento realmente vence.
- Separa a frequência do mapa da frequência dos monitores: uma atualização de
  posição não recalcula combate, status ou drops antes do prazo próprio.
- Reutiliza os componentes de jogadores próximos quando os dados não mudaram,
  evitando destruir e recriar cartões e imagens a cada atualização.
- Mantém intactos o banco existente, as capturas, sessões e configurações.

## 2.0.0-beta.2 — 2026-08-21

- Move o status para o cartão **Sessão atual** e separa o início em **Começar
  captura nova** e **Continuar captura anterior**, sem oferecer descarte da
  sessão pendente na interface 2.0.
- Adiciona **Resumo Geral**, com cartões compactos por cliente. O cabeçalho reúne
  personagem, Classe/Biosuit, Rover, imagens e diamantes; o corpo mostra barra
  de EXP, tempo, ganho de EXP, créditos atuais/da sessão e contribuição total/h.
  O relógio individual começa no primeiro reconhecimento do cliente.
- Separa anúncios de drops de outros jogadores em aba própria, com os mesmos
  filtros e paginação de Drops, consolidando mensagens simultâneas capturadas
  por mais de um cliente.
- Mantém os cartões **Sessão atual** e **Subsessão ativa** independentes, combina
  o valor bruto e percentual de XP/h e remove Drops recentes e Mobs próximos da
  Visão geral.
- Restaura **Criar a próxima automaticamente**, com intervalo configurável:
  a expiração normal por duração abre a próxima subsessão; encerramentos por
  teleporte, morte ou 30 segundos sem kill continuam sem iniciar outra.
- Reúne Profile, API local e saúde do programa dentro de **Configurações** e
  remove os itens laterais **Integrações** e **Tutorial**.
- Usa identidades confirmadas do Top 100 para completar guildas no combate,
  incluindo **Blood**, e volta a exibir as imagens de Classe e Rover.
- Torna a planta da Visão geral uma miniatura quadrada de até 420 px, sem zoom,
  arraste ou recentralização. Personagem, área de proximidade e jogadores ficam
  ancorados às coordenadas da planta; a navegação permanece na aba **Mapa**.
- Classifica drops épicos no cartão da sessão como arma, armadura, acessório,
  expansão, Blueprint de MAU ou Blueprint de Launcher a partir do catálogo
  oficial 1.28.5.
- Prepara o envio idempotente e sanitizado do Banco de Leilão para
  `/api/import/auction-bank`. A consolidação de guilda e o alerta de undercut
  permanecem no site/2.1; o programa somente envia e apresenta avisos.
- Torna regressão um gate obrigatório: toda adição exige teste específico e a
  suíte automática completa antes de ser considerada concluída.
- Corrige a regressão que desativava definitivamente o vínculo dos clientes
  após a substituição dos processos/conexões. As novas rotas voltam a ser
  acompanhadas e são realinhadas pelo UID canônico antes de atribuir EXP,
  contribuição e recompensas.
- Migra bancos afetados recuperando eventos sem personagem somente quando eles
  compartilham o mesmo fluxo TCP de uma identidade canônica única; registros
  ambíguos permanecem sem dono para impedir mistura entre clientes.
- Corrige a atualização rápida que deixava os monitores e cartões sem dados por
  referenciar o histórico do Ranking de EXP fora do contexto correto.
- Corrige o placar do Boss para ordenar jogadores, grupos e guildas pelo dano
  acumulado do encontro; a taxa exibida passa a ser a média desde o primeiro
  golpe, separada do indicador instantâneo de queda de HP.
- Normaliza fluxos TCP nos dois sentidos para preservar a identidade e o alvo
  atual do Monitor PvP em rotas com ExitLag, sem misturar clientes.
- Adiciona a vida própria acima do alvo atual no overlay PvP.
- Acumula drops idênticos por cliente/personagem, com primeiro/último horário e
  ocorrências, e permite selecionar múltiplas categorias de raridade para som.
  A origem é exclusivamente o evento de recompensa confirmado pelo servidor,
  sem leitura textual do chat.
- Materializa o histórico do Top 100 com data/hora, nível, progresso, EXP ganha
  e projeções por hora entre capturas, descartando resultados idênticos
  observados dentro da mesma janela de uma hora.
- Padroniza todas as tabelas para permitir redimensionamento e reordenação das
  colunas, com ajuste automático ao dar duplo clique no cabeçalho.
- Amplia o histórico próprio do leilão com compras confirmadas, vendas e tipos
  brutos ainda não validados, sem expor IDs internos.
- Adiciona os campos MAU, launcher e poção de EXP às subsessões em estado
  explícito `Aguardando captura validada`; nenhum uso é inferido antes das séries
  marcadas exigidas pelo protocolo de evidência.
- Sob pressão do limite de RAM escolhido, compacta eventos efêmeros, entidades
  antigas e buffers TCP, preservando o estado recente e o conteúdo persistido.

- Prepara o perfil portátil `2.0.0-rc1 (Homologação)`, com estado DPAPI e
  instância Windows isolados, emissor v3 somente em `127.0.0.1:8788`, chave
  pública de staging incorporada e integração remota restrita à validação do
  Profile e aos envios idempotentes do Mercado, Ranking de EXP e Banco de
  Leilão. Cada Top
  100 completo novo é enviado automaticamente; sessões, inventário e bancos
  continuam sem permissão de envio. O perfil recusa instalador e release.
- Adiciona catálogo versionado de 508 mapas da tabela 1.28.5, com 496 nomes
  PT-BR, 504 nomes EN-US e fallback seguro por idioma/índice.
- Embarca 49 plantas cartográficas para Novus, Albern Crater, Android Junkyard,
  Secret Nemesis Base, campos de mineração e instalações orbitais. Novus é
  dividido em 56 regiões oficiais, com centro, área dos spawns estáticos e
  referência regional conforme a posição; layouts compartilhados entre andares
  guardam a origem e a evidência da reutilização, enquanto a tela mostra a planta inteira.
- Trata andares como regiões do mapa-base: por exemplo, o MapIndex 638 é
  exibido como mapa **Ferro-Velho de Androides** e região **8F**. A regra também
  alimenta o preenchimento automático de subsessões em Android, Nemesis e
  campos de mineração.
- Expõe a região resolvida e seu centro sanitizado no cartão de mapa e em
  `/api/v1/map`, usando proximidade ao centro oficial sem inventar fronteiras.
- Exibe a planta inteira por padrão e adiciona zoom, arraste livre e botão
  **Focar personagem** ao cartão de mapa. A posição passa a usar prévia efêmera
  a cada 1 segundo mesmo sem monitores ligados, sem persistir trilha de movimento.
- Corrige o mapa manual para preservar também o índice da planta selecionada.
  Preferências anteriores que guardavam apenas mapa e região são migradas em
  memória, permitindo exibir imediatamente a planta do Android Junkyard 9F e
  dos demais mapas preparados sem exigir nova seleção.
- Troca a entrada livre do mapa manual por uma lista pesquisável do catálogo;
  ela só identifica mapas não reconhecidos e nunca desativa a leitura automática.
- Define Farm por dano local ou abate confirmado de mob nos últimos 30 segundos
  e fixa a prioridade visual `Teleportando > PvP > Farm > Ocioso`; Boss permanece
  como sinal independente de proximidade.
- Mostra o ícone real de cada item nos drops recentes e aplica cores semânticas
  de Comum, Incomum, Raro, Épico e Lendário conforme o catálogo.
- Isola o cartão **Drops recentes** pelo cliente selecionado, sem misturar os
  itens capturados pelos demais clientes.
- Mantém os cartões **Sessão atual** e **Subsessão ativa** separados na Visão
  geral; a subsessão informa claramente quando não há uma em andamento.
- Acrescenta Nível e EXP % ao Top 100, calculados a partir da EXP total com a
  curva oficial 1.28.5 já embarcada.
- Adiciona protocolo dedicado do Banco PvE com lotes idempotentes de até 500
  registros, localização múltipla, conflitos de HP e ack explícito por item;
  o código do site está preparado, mas não foi implantado.
- Integra o decoder de mapa atualizado: respostas de teleporte passam a fornecer
  o `map_index` confirmado e `0x040A` permanece apenas como fonte de posição,
  impedindo que o antigo valor bruto seja exibido como mapa.
- Mantém no stream em memória as solicitações e respostas de teleporte já
  decodificadas, permitindo que o módulo Mapa atualize automaticamente após a
  troca de mapa.
- Consolida PvE, PvP e Boss em uma única área de Monitoramento, preservando os
  módulos e permissões independentes.
- Remove **Mobs próximos** e **Drops recentes** da Visão geral para concentrar
  esses dados nas respectivas áreas dedicadas.
- Mostra no Monitor PvE uma barra com a última vida confirmada do personagem,
  posicionada acima da barra de vida do alvo atual e isolada por cliente.
- Corrige o Monitor Boss de um único cliente quando o jogo abre os fluxos
  lógico e de combate em portas locais diferentes: os eventos continuam
  isolados e passam a alcançar o cliente confirmado, sem relaxar o roteamento
  quando existem dois ou mais clientes.
- Consolida sessão atual/envios e histórico/subsessões na área **Sessões**;
  Profile, API local e a saúde sanitizada de captura, memória, checkpoint e
  stream ficam reunidos em **Configurações**.
- Confirma automaticamente mapa, spot e mobs da subsessão somente após leituras
  estáveis, ignora mobs transitórios e registra origem/confiança da inferência.
- Mantém o Banco PvP compatível e congela novas alterações funcionais para a
  versão 2.1.
- Prepara no programa 2.0 o contrato de envio do Banco de Leilão; banco
  consolidado do site, API de guilda e anti-undercut permanecem na versão 2.1.
  O histórico local próprio de compras e vendas continua na 2.0.
- Define que ensaios reais de memória/dois clientes e todas as validações
  manuais ou visuais serão executados somente após gerar o executável candidato.
- Mantém implementação, testes e documentação sem release ou deploy de
  produção. Um instalador de homologação isolado pode ser
  gerado explicitamente sem substituir a instalação RF QOL normal.

## Em desenvolvimento — diagnóstico

- Mantém o log técnico detalhado sempre ativo desde a abertura do RF QOL,
  ignorando preferências antigas que o desativavam. A sanitização de chaves,
  tokens, endereços e conteúdo bruto de pacotes permanece obrigatória.
- Aceita rotas secundárias criadas pelo ExitLag quando pertencem ao mesmo
  processo do ProjectRF e associa o fluxo do monitor PvP ao cliente pela UID
  confirmada, sem capturar conexões do serviço do ExitLag nem registrar
  endereços, portas ou pacotes no diagnóstico.

## 1.0.8 — instalação manual

- Integra os layouts confirmados mais recentes para movimento, saída de sala,
  desaparecimento de entidades, teleporte e troca de slots de equipamento.
- Remove imediatamente do estado vivo os jogadores e monstros informados pelo
  servidor como fora de alcance, sem aguardar somente o vencimento de quinze
  segundos do Monitor PvP.
- Preserva a leitura de alvo atual, o pedido de habilidade, os dois formatos já
  observados de equipamento e as validações defensivas existentes no RF QOL.

## 1.0.7 — instalação manual

- Corrige o Monitor PvP para que pacotes de combate com UID reutilizado não
  renovem personagens vistos anteriormente em outro mapa. A permanência na
  lista de próximos agora depende da última aparição confirmada e vence após
  quinze segundos.

## 1.0.6 — instalação manual

- Mantém o alvo atual no topo do Monitor PvP, antes de jogadores próximos.
- Remove jogadores hostis vencidos da aba e do overlay pelo relógio da
  interface, mesmo quando nenhum pacote novo chega.

## 1.0.5 — instalação manual

- Permite configurar o Monitor PvP entre 0,5 e 60 segundos, com padrão de
  1 segundo e passo de 0,5 segundo.
- Verifica os vencimentos dos monitores a cada 250 ms, sem iniciar nova leitura
  rápida enquanto o resultado anterior ainda estiver sendo processado.
- Mantém o alvo atual no intervalo escolhido e limita a reconstrução das listas
  e overlays de jogadores próximos a uma vez por segundo.
- Adiciona modos de foco independentes em Boss e PvP: os monitores ligados
  continuam rápidos e as leituras gerais passam a cada cinco minutos.
- Calcula apenas os monitores ativos no stream em memória e roteia os eventos
  uma única vez por cliente.
- Corrige o DPS por guilda usando a janela completa, expira bosses antigos,
  recusa rotas ambíguas e impede a sobreposição de workers do decoder.
- Corrige a lista de próximos do Monitor PvP separando sua presença da limpeza
  de três segundos do alvo atual.
- Impede que eventos vencidos e fora de ordem se acumulem no monitor e remove
  a reconstrução integral do Banco PvP a cada atualização de combate.
- Mantém os overlays sem reconstrução durante o arraste.
- Inclui UID persistente e guilda observada no ranking de Boss para completar
  nomes pelo banco local/final e recalcular a soma por guilda.

## 1.0.4 — instalação manual

- Consolida as correções de Banco PvP, inventário e envios preparadas após a
  1.0.3.
- Corrige o ciclo de vida do Monitor PvP para remover personagens antigos,
  reconhecer a identidade atual e limpar os overlays ao desligar o monitor.
- Mantém distribuição manual, sem Authenticode e sem atualização automática.

## 1.0.3 — instalação manual

- Consolida as correções e recursos em desenvolvimento descritos abaixo em
  um novo instalador completo, mantendo atualização manual e sem Authenticode.
- Separa envio e recebimento do Banco PvP, adiciona filtros, edição em lote e
  preserva posição e largura das colunas.

## Em desenvolvimento — Banco PvP, Inventário e Envios

- Permite editar qualquer guilda no Banco PvP, adiciona o status Ignorar e
  oculta os UIDs ignorados sem impedir a sincronização com outros clientes.
- Integra o decoder de `guild_id` e das listas inimiga/aliada para preencher
  guilda e status PvP observados automaticamente, preservando edições manuais.
- Adiciona Classe, derivada do biosuit, e Rover ao Banco PvP; os códigos
  observados passam pela aprovação temporário/final e o rover respeita o idioma
  configurado para os dados do jogo.
- Substitui o envio a cada edição por intervalo configurável de 1 a 60 minutos,
  padrão de 5 minutos, e separa `Enviar ao site`, `Receber do site` e a
  atualização estritamente local.
- Adiciona filtros de texto/status, seleção e edição em lote e preservação da
  ordem e largura ajustadas das colunas do Banco PvP.
- Troca a seleção implícita por caixas de seleção em cada UID e permite aplicar
  somente guilda, somente status ou ambos aos registros marcados.
- Aceita respostas maiores do Banco Final sem confundir JSON truncado com uma
  página de acesso, mantendo limite máximo de segurança.
- Restringe `Enviar ao site` do Banco PvP aos personagens; mobs e HP não fazem
  mais parte desse pacote. HP desconhecido legado também é normalizado.
- Corrige a reconstrução do inventário para preservar itens com slots repetidos
  usando o UID de cada instância.
- Permite definir a categoria de um item pelo menu de contexto e reaplica a
  escolha local pelo código do item.
- Adiciona envio de Inventário e Tudo por cliente; os botões mostram o
  personagem reconhecido e o site persiste o inventário sanitizado por UID.

## Em desenvolvimento — Banco e overlays PvP

- Separa o PvP em overlays móveis de alvo atual, próximos hostis e próximos
  não hostis, sempre limitados ao cliente selecionado.
- Remove jogadores remotos sem confirmação após três segundos, limita a janela
  efêmera de combate e mantém somente a identidade local necessária, evitando
  que entidades antigas ocupem o monitor e atrasem o reconhecimento das novas.
- A identidade recebida ao vivo substitui a identidade antiga da sessão; ao
  desligar o monitor do cliente, os três overlays são limpos imediatamente.
- Adiciona Banco PvP com UID, personagem, guilda e status manual
  Aliado/Inimigo/Neutro, usando a sincronização sanitizada já existente.

## Em desenvolvimento — Inventário

- Decoder canônico de snapshots/deltas de inventário integrado à captura.
- Nova aba Inventário por cliente PC/emulador, com ícones, filtro e quantidades.
- Subabas Equipamentos, Consumíveis, Materiais, Talicas, Partes de Rover e
  Outros, classificadas pelos metadados oficiais do jogo 1.28.5.
- Payload sanitizado `capture.inventory` preparado no envio de Personagem.
- Nomes sem tradução portuguesa usam o catálogo inglês antes do identificador
  genérico, incluindo os materiais Greater e Superior.

## Em desenvolvimento — Idioma dos dados do jogo

- A opção de idioma agora se aplica de forma única somente aos dados do jogo:
  itens, inventário, equipamento, Mercado, mapas, spots, mobs, bosses,
  Biosuits e Rovers. A interface do RF QOL permanece em português.
- Exibição, exportação e envio usam o mesmo catálogo selecionado, com fallback
  para o outro idioma quando a tradução ainda não existe.

## Em desenvolvimento — Seleção de UID

- Remove o botão separado de UID e a função de renomear clientes.
- O duplo clique em Cliente A/B ou Emulador abre a seleção manual de UID; os
  rótulos dos slots permanecem fixos e exibem o personagem capturado.

## 1.0.0 — candidato para instalação manual

- renomeia produto, executável e instalador para RF QOL e mantém a identidade visual Karvalho;
- adiciona o link oficial do Discord;
- substitui a lease v1 por lease v2 com chaves pinadas, produto/audience, instalação e teto offline de 24 horas;
- usa licenças novas com prefixo RFQ e rejeita licenças KRV da linha anterior;
- implementa estados explícitos de autorização e introspecção v2 obrigatória no site;
- bloqueia captura, leitura, monitores, exportação e envio sem licença válida no motor compartilhado;
- separa Base, Monitor PvE, Monitor PvP e Monitor Boss na lease assinada; sem
  permissão, PvE/PvP continuam visíveis e bloqueados enquanto Boss fica oculto;
- separa o overlay Boss em dois controles móveis e independentes: vida e DPS;
- compacta o overlay PvP e limita sua leitura ao alvo atual do personagem
  vinculado à aba selecionada, sem agregar jogadores ou outros clientes;
- remove os atalhos F1–F4 dos envios, preservando os botões e os atalhos de
  captura e monitores;
- separa as chaves de licença e atualização e remove a chave mutável do estado local;
- implementa manifesto de update v2, anti-downgrade e reverificação de tamanho/hash;
- substitui o rollback por cópia executável por instalador anterior, manifesto
  dedicado Ed25519, compatibilidade assinada, cache administrativo e backup
  SQLite verificado;
- separa estado de confiança e staging em diretório de máquina com ACL administrativo;
- fecha dependências e adiciona lock de wheels com SHA-256 para Windows x64/Python 3.13;
- registra a decisão de distribuir executável e instalador sem Authenticode;
- define instalação manual para a 1.0: não consulta feed, não baixa executável,
  abre o Discord oficial para avisos e gera `SHA256SUMS.txt` no build de release;
- permite distribuir o instalador pela branch pública de download sem promover
  o candidato a GitHub Release; o G4 de release permanece separado.
- fixa a pública definitiva de lease `lease-2026-01`; a privada continua fora
  do repositório e a chave offline de update fica adiada enquanto o modo for manual.
- prepara a cerimônia offline de update com duas cópias privadas cifradas,
  restauração verificada e assinatura direta a partir do PEM protegido;
- corrige o texto da ativação para informar o limite offline real de 24 horas;
- adiciona vetor público, contrato do emissor, cerimônia de chaves e runbook de release.
- corrige o envio ao site para validar a lease v2 no endpoint, produto e público
  definitivos do RF QOL;
- evita que a autenticação do Profile dispute a escrita do banco com importações
  e alertas de Mercado;
- mostra o estado do envio automático de Mercado e aguarda 60 segundos antes de
  uma nova tentativa após falha;
- mantém os envios de Codex e Memory Chips bloqueados até existir um pacote real
  do respectivo tipo, mesmo durante uma captura ativa.
- preserva por UID o último snapshot completo de Codex e Memory Chips entre
  sessões de captura e aplica as adições posteriores antes de exibir ou enviar.

## 3.0.11 — beta

- impede que várias instâncias do programa sejam abertas ao mesmo tempo e restaura a janela já existente;
- mantém no ícone da bandeja as ações de abrir e sair e remove o ícone ao encerrar, evitando ícones duplicados ou sem menu;
- corrige a inversão de experiência, contribuição e demais eventos entre os Clientes A e B usando UID confirmado e nível histórico para preservar a rota física correta;
- remove da seleção subsessões que já foram excluídas, evitando o aviso falso de uma subsessão marcada.

## 3.0.10 — beta

- permite arrastar o overlay PvP e preserva sua posição entre aberturas;
- reposiciona o overlay automaticamente se a posição salva ficar fora da tela;
- alimenta o overlay PvP imediatamente com o alvo atual e com jogadores hostis próximos confirmados, sem tomar o foco da tela;
- prioriza e preserva eventos de Boss mesmo sob grande volume de tráfego paralelo;
- mantém a identidade e o estado do Boss fora do buffer comum até morte confirmada;
- exibe fila, atraso e contadores do leitor em tempo real e reinicia o leitor se o trabalhador parar.

## 3.0.9 — beta

- lê o alvo selecionado diretamente dos pedidos `0x0609` e `0x0601` do cliente;
- mantém o alvo PvE/PvP funcional mesmo quando o personagem local não aparece em `0x0305`;
- diferencia outra captura já ativa de uma interrupção real ao iniciar;
- registra no log o tipo e a mensagem completos das falhas de captura.

## 3.0.8 — beta

- separa os monitores PvE e PvP em abas dos Clientes A e B, com ativação independente;
- corrige o alvo PvE em ataques de área usando o alvo principal confirmado pelo protocolo;
- limita o monitor PvE a NPCs com nomes definidos no catálogo;
- remove jogadores próximos antigos após cinco segundos sem nova confirmação;
- move o filtro numérico de nível para antes da lista de mobs e compacta seus campos;
- move a observação para baixo do cliente e remove a linha redundante de nível dos mobs.

## 3.0.7 — beta

- corrige a assinatura da API nativa do Windows usada para medir a memória;
- volta a exibir no topo o consumo atual de RAM do RF NEXT QOL;
- adiciona teste real do contador de memória, sem depender de valor simulado.

## 3.0.6 — beta

- mostra na aba Boss somente os clientes que detectaram ao menos um Boss;
- faz um único cartão ocupar toda a largura quando só um cliente detectar Boss;
- amplia o ranking para até 10 jogadores com DPS e dano na janela de 10 segundos;
- separa os rankings por jogador, guilda e grupo quando essas identidades estiverem disponíveis.

## 3.0.5 — beta

- permite alterar individualmente os atalhos globais dos monitores PvE, PvP e Boss;
- aplica os novos atalhos imediatamente e os preserva entre atualizações;
- permite habilitar ou desabilitar o envio automático de Leilão/Mercado;
- mantém o envio manual de Mercado disponível quando o automático está desligado.

## 3.0.4 — beta

- corrige a cópia recursiva da instalação para dentro do próprio rollback;
- exclui banco, capturas, logs, cache e atualizações do backup local;
- limita o rollback a 1 GiB e cancela a atualização se o backup falhar;
- preserva somente os binários, a licença e as preferências necessárias.

## 3.0.3 — beta

- preserva o último Biosuit/classe e Rover confirmados para cada UID;
- restaura esse estado histórico ao selecionar um personagem conhecido;
- substitui o estado histórico assim que uma captura atual confirma novos dados;
- impede que o Rover de personagens próximos atualize o histórico do UID.

## 3.0.2 — beta

- impede corte e sobreposição nos cartões dos monitores PvE e PvP;
- divide os Clientes A e B em duas colunas no modo maximizado ou tela cheia;
- mostra o HP atual bruto, em vez do percentual, nos mobs próximos.

## 3.0.1 — beta

- mantém um histórico persistente dos UIDs canônicos reconhecidos;
- permite selecionar por cliente um personagem conhecido anteriormente;
- impede que o mesmo UID seja vinculado simultaneamente aos dois clientes;
- corrige automaticamente uma seleção manual quando a captura confirma outro UID.

## 3.0.0 — beta

- mostra o consumo atual de memória RAM no topo;
- permite encerrar a captura sem ler os arquivos, preservando-os para retomada;
- melhora espaçamento e legibilidade dos cartões dos monitores;
- torna transparentes os fundos dos overlays de PvP e Boss;
- torna visíveis os atalhos globais dos monitores PvE, PvP e Boss;
- filtra e deduplica jogadores PvP apenas por identidade confirmada e recente;
- alinha o loot das subsessões ao contrato numérico aceito pelo site.

## 2.1.7 — 2026-08-06

- corrige o contraste do seletor de colunas e dos demais menus Qt;
- mantém fundo escuro, texto legível, seleção dourada e separadores visíveis.

## 2.1.6 — 2026-08-06

- adiciona a opção de log completo com registros detalhados e sanitizados;
- corrige o contraste de todas as mensagens e traduz os botões para Português.

## 2.1.5 — 2026-08-06

- mantém a leitura durante a captura quando a prévia nativa do PktMon não inicia;
- alterna segmentos ETL automaticamente e preserva o erro original no log.

## 2.1.4 — 2026-08-05

- impede o watchdog de encerrar o PktMon por parâmetros vazios;
- interpreta em UTF-8 e reconhece o status detalhado do PktMon em português;
- evita repetir continuamente o mesmo aviso de status desconhecido no log.

## 2.1.3 — 2026-08-05

- evita que respostas desconhecidas do `pktmon status` interrompam a captura;
- exige três confirmações consecutivas antes de considerar o PktMon encerrado;
- registra no log a resposta desconhecida ou que confirmou a interrupção.

## 2.1.2 — 2026-08-05

- permite escolher quais informações aparecem no histórico de subsessões;
- permite reordenar e redimensionar as colunas, preservando a preferência;
- mantém a seleção fixa na primeira coluna e remove Diamantes das opções.

## 2.1.1 — 2026-08-05

- exibe o tempo transcorrido de cada subsessão no histórico;
- mostra os níveis mínimo e máximo ao lado de cada mob da localização;
- atualiza imediatamente o nome da subsessão ativa após editar.

## 2.1b — 2026-08-05

- substitui a interface principal pelo rework Qt, mantendo captura, licença,
  atualização, exportação, envios e atalhos da versão anterior;
- exibe os dois clientes em cartões equivalentes na tela cheia e mantém um
  cartão por linha no modo de janela;
- mostra classe, Biosuit e a imagem real do Rover pelo `rover_item_index`;
- corrige associação de personagem, Rover e equipamentos, leitura contínua,
  envios de personagem/Codex/Memory Chips e separação de mercados por servidor;
- preserva recuperação de sessões, subsessões, logs, atualização assinada e
  rollback da instalação 2.0n.

## 2.0n — 2026-08-03

- impede que atalhos globais tragam o programa ao primeiro plano; avisos desses
  envios ficam somente no painel.

## 2.0m — 2026-08-03

- corrige os atalhos globais usando uma fila de mensagens própria, evitando que
  o loop da interface consuma `WM_HOTKEY` antes do envio ser acionado.

## 2.0l — 2026-08-03

- registra os atalhos configuráveis dos envios rápidos como hotkeys globais do
  Windows, permitindo usá-los com o programa minimizado ou em segundo plano.

## 2.0k — 2026-08-03

- mostra na subsessão a quantidade estimada de mobs abatidos no intervalo e
  inclui `mob_kills_estimated` no relatório enviado ao site.
- adiciona filtros por cliente, andamento e envio e permite mostrar 5, 10, 20
  ou 50 subsessões por página, com 10 como padrão.
- adiciona caixas `☐/☑` e preserva a seleção de subsessões ao trocar página,
  filtro ou atualizar as informações.

## 2.0j — 2026-08-02

- corrige a atualização automática da tabela de subsessões, usando o ID da
  linha em vez do registro completo ao recalcular a largura das colunas.

## 2.0i — 2026-08-02

- abertura, troca de abas e troca de cliente deixam de reler o histórico na
  thread visual; snapshots são calculados em segundo plano e resultados
  obsoletos são descartados;
- resumos da visão geral e das subsessões passam a processar somente eventos
  novos em lotes limitados, mantendo exportação e envio no envelope canônico;
- o ciclo visual de um segundo deixa de consultar banco, Pktmon e conexões de
  rede sincronamente;
- tela cheia passa a mostrar os cartões, classe, Rover e métricas dos dois
  clientes; envios identificam Cliente A e Cliente B;
- controles da captura ficam na barra superior, a aba passa a se chamar
  Envios e os controles automáticos ficam no formulário de subsessão;
- encerramento manual não recria subsessão automática, campos readonly ganham
  contraste explícito e o watchdog usa timeout de heartbeat de 60 segundos.

## 2.0h — 2026-08-02

- a visão geral mostra a subsessão ativa e divide os dados entre Cliente A e
  Cliente B quando a janela está maximizada;
- Personagem, Codex e Memory Chips possuem envios separados por cliente, com
  equipamentos incluídos no envio de personagem;
- subsessões guardam o cliente, podem ser selecionadas, editadas, renomeadas,
  excluídas ou enviadas ao site;
- o histórico centraliza e ajusta automaticamente as colunas;
- o tamanho do arquivo atual é atualizado separadamente do total armazenado;
- Rover e equipamentos só aceitam eventos vinculados ao UID correspondente.

## 2.0g — 2026-07-31

- a captura e o decoder usam exclusivamente as portas RF NEXT confirmadas;
- portas HTTPS, efêmeras e históricas não são mais acumuladas entre
  reconexões, reduzindo pacotes estranhos e eventos não decodificados.

## 2.0f — 2026-07-31

- a sessão anterior pendente relê os segmentos para recuperar o UID do
  personagem, sem exigir uma nova entrada no jogo;
- o bloco de nova subsessão pode ser recolhido, os mobs têm seleção total e
  as listas suspensas usam texto preto sobre fundo claro.

## 2.0e — 2026-07-31

- subsessões selecionadas podem ser renomeadas ou excluídas localmente;
- exclusão preserva os eventos da captura e dados já enviados ao site;
- seleção de mobs usa caixas de marcação em três colunas e remove prefixos
  técnicos dos nomes exibidos.

## 2.0d — 2026-07-31

- localização, spot e mobs podem ser exibidos em Português ou English;
- a captura mantém um heartbeat supervisionado pela interface;
- se o aplicativo encerrar ou parar de responder por 45 segundos, o vigia
  local encerra o PktMon e remove os filtros para impedir arquivos excessivos.

## 2.0c — 2026-07-30

- EXP, créditos e contribuição do farm passam a usar a recompensa-base do
  monstro; o bônus de finalização não infla mais os totais nem as taxas.
- Finalizações são contabilizadas separadamente e pacotes sem recompensa de
  EXP não são considerados abates.
- O loot é separado em comum, incomum, raro e épico usando os 8.192 itens da
  base canônica 1.28.5.
- A visão geral e as subsessões exibem os totais corrigidos, incluindo
  contribuição total e por hora.
- O envio de personagem inclui os equipamentos e a pasta das capturas pode
  ser escolhida nas configurações.

## 2.0b — 2026-07-30

- O catálogo de farm passa a usar seleção encadeada de mapa, spot e mobs.
- A subsessão aceita mob extra, nível, observação e duração própria; duração
  `0` permanece ativa até o encerramento manual.

## 2.0a — 2026-07-30

- O Rover equipado na entrada é lido diretamente do `0x0305` do próprio
  personagem; não é mais necessário trocar o Rover para exibi-lo.

## 1.0.24 — 2026-07-30

- O leitor incremental reutiliza a correlação canônica entre aparência e
  inventário para exportar os equipamentos ativos.
- Personagem, Codex e Memory Chips enviam cargas separadas; Codex envia apenas
  coleções e Memory Chips envia apenas chips.
- O site aceita o resumo de captura antigo como fallback para classe, nível,
  Biosuit, Rover e equipamentos, e recarrega os dados ao voltar para a janela.

## 1.0.23 — 2026-07-30

- Personagem, Mercado, Codex e Memory Chips passam a enviar ao site os dados
  já lidos pela captura contínua; os botões e atalhos não iniciam novas
  capturas.
- O encerramento mostra o progresso real da leitura por segmento.
- Subsessões encerradas podem ser selecionadas e enviadas individualmente,
  com identificador cumulativo persistente e proteção contra duplicidade.

## 1.0.22 — 2026-07-30

- O aplicativo passa a se chamar RF NEXT QOL e exibe o novo logo junto ao
  símbolo do urso com K.
- O ícone da classe usa a cor da raridade confirmada pelo `Grade` do Biosuit.
- Trocas de Biosuit confirmadas durante a captura atualizam classe, nome,
  raridade e ícone sem aguardar o encerramento da sessão.
- O Rover equipado é identificado por eventos confirmados, exibido com nome e
  ícone à esquerda da classe; solicitações e respostas com erro são ignoradas.

## 1.0.21 — 2026-07-30

- O mesmo token de Profile autentica os envios de Farm, Codex, Memory Chips
  e Mercado.
- Capturas rápidas decodificadas são enviadas em segundo plano sem encerrar a
  captura contínua; falhas ficam pendentes no banco local para nova tentativa.
- Codex e Memory Chips são mesclados ao progresso existente, sem apagar
  coleções que não estavam na captura rápida.

## 1.0.20 — 2026-07-30

- Iniciar com “Descartar sessão anterior” não consulta o Pktmon nem apresenta
  erro quando existe apenas um identificador antigo, sem arquivos reais.
- Cada subsessão pode receber uma duração própria em minutos e é encerrada
  automaticamente no prazo informado.
- O catálogo 1.28.5 de localização, mob e nível passa a acompanhar o programa;
  escolher a localização filtra os mobs e preenche o intervalo de níveis.
- O histórico e o JSON das subsessões incluem EXP total, EXP total em
  percentual, EXP/h e EXP/h em percentual.

## 1.0.19 — 2026-07-30

- A leitura ao vivo usa segmentos fechados por intervalo e continua gravando
  em paralelo, sem o limite permanente de 512 MB da prévia.
- Os clientes exibem separadamente o nome manual e o nome capturado; o nome
  manual não identifica nem renomeia dados exportados.
- As durações mostram segundos ou minutos e todas as páginas possuem rolagem
  vertical e horizontal quando o conteúdo ultrapassa a janela.
- O aplicativo e a bandeja usam o símbolo do urso com K.

## 1.0.18 — 2026-07-29

- Segmentos residuais vazios não anulam mais os eventos decodificados nem
  deixam a sessão presa em reanálise.
- A retomada automática é interrompida quando existe uma falha real pendente.
- Em uma sessão de cliente único, o `0x0106` canônico vincula o personagem ao
  Cliente A mesmo depois de uma troca de porta não observada pelo Windows.
- Uma identidade heurística nunca substitui a identidade canônica e é
  recusada quando o mesmo pacote contém mais de uma aparição de personagem.
- O preview bruto é preservado quando nenhuma rota de cliente corresponde aos
  pacotes, permitindo a decodificação após relog ou troca de porta.

## 1.0.17 — 2026-07-29

- Mantém o histórico de portas de cada cliente durante reconexões e na
  análise final.
- Identifica o personagem somente pela sequência completa de entrada marcada,
  dentro da janela escolhida e numa porta confirmada do Cliente A/B.
- Não usa aparições comuns de outros jogadores como identidade do usuário.

## 1.0.16 — 2026-07-29

- Alternar Cliente A/B não abre mais a edição do nome; cada cliente possui um botão Renomear.
- Novas conexões permanecem vinculadas ao processo correto durante a captura ao vivo.
- EXP, Loot e personagem são atualizados nas leituras periódicas, sem aguardar Parar.
- EXP faltante e EXP/h (%) usam a exigência correta do próximo nível.
- Diamantes são exibidos somente quando UID ou nome confirmam o próprio personagem.
- Cada captura rápida possui duração própria entre 10 e 300 segundos.
- Os quatro cartões de captura rápida usam a mesma altura e alinhamento.

## 1.0.15 — 2026-07-29

- Separa automaticamente Cliente A e Cliente B pelas portas de cada processo.
- Mantém a separação nas leituras ao vivo e na análise final dos segmentos.
- Usa somente a entrada do próprio personagem para confirmar UID e nome.
- Remove a logo Karvalho do cartão reservado ao símbolo da classe.

## 1.0.14 — 2026-07-29

- Capturas rápidas agora aceitam duração configurável de 10 a 300 segundos.
- Atalhos receberam contraste dourado nos cartões e nas configurações.
- Removidas bordas internas que atravessavam textos e dados dos painéis.
- Cabeçalho e marca lateral foram redimensionados para aproveitar melhor o espaço.

## 1.0.13 — 2026-07-29

- Adicionada opção confirmada para limpar a sessão anterior antes de iniciar.
- A limpeza inclui arquivos brutos ainda não decodificados e os envia à Lixeira.
- O histórico, as janelas de captura e as subsessões da sessão descartada também são removidos.

## 1.0.12 — 2026-07-29

- alinha a estrutura das quatro telas ao mockup aprovado;
- corrige o cronômetro para não avançar com a captura parada;
- torna explícitos os estados disponível, ativo, pausado e encerrado;
- recupera e analisa uma captura pendente antes de iniciar a próxima;
- habilita pausa e continuação da mesma sessão.

## 1.0.11 — 2026-07-29

- recompõe as telas conforme o mockup aprovado com fontes e marca Karvalho;
- corrige a validação do token do Profile pela API pública autenticada;
- corrige capturas rápidas e subsessões durante a captura contínua;
- detecta automaticamente o executável `ProjectRF` conectado;
- amplia o autoteste do instalador para construir toda a interface.

## 1.0.10 — 2026-07-29

- valida a licença salva em segundo plano ao abrir e atualiza o estado da tela;
- atualiza informações durante a captura usando o preview nativo do PktMon;
- preserva a captura ETL completa como fonte da exportação.

## 1.0.9 — 2026-07-28

- portas locais e remotas do `ProjectRF` passam pela captura e pela análise;
- a porta RF `12010` entra no conjunto conhecido e recupera eventos antes
  presentes no ETL, mas ignorados pelo decoder;
- a parada é idempotente e impede análises concorrentes da mesma sessão;
- ETL sem pacotes permanece pendente e preservado para nova análise;
- mudanças no decoder, catálogo ou portas reprocessam capturas antigas;
- a tela exibe os contadores de pacotes do PktMon quando disponíveis;
- o parser PCAPNG valida blocos truncados e informa diagnóstico seguro;
- fluxos TCP com gap tentam ressincronização somente após três frames válidos.

## 1.0.8 — 2026-07-28

- a exportação pergunta a EXP atual quando há um UID confirmado e eventos
  restantes sem identificação;
- o fluxo de EXP mais próximo é associado ao personagem confirmado;
- o CSV de captura inclui licença, instalação e marcações de Codex para
  importação segura no site;
- o site distingue CSV de captura de CSV de Mercado pelo cabeçalho.

## 1.0.7 — 2026-07-28

- removida a seleção manual de processo por personagem introduzida na 1.0.6;
- todas as conexões dos clientes `ProjectRF` são capturadas automaticamente;
- PID, porta e ordem dos processos não são usados como identidade de personagem;
- a separação usa somente UID confirmado ou a EXP (%) informada na exportação.

## 1.0.6 — 2026-07-28

- cada nome de personagem é vinculado explicitamente a um processo `ProjectRF`;
- portas locais de cada processo identificam os eventos sem depender da
  presença eventual do UID no protocolo;
- filtros das portas conhecidas do jogo já ficam ativos antes do login e
  continuam cobrindo reconexões;
- exportações incompletas geram alerta e marca de revisão, sem bloquear os
  arquivos JSON/CSV;
- sem UID, a EXP atual (%) informada associa cada personagem à conexão mais
  próxima; eventos restantes seguem em arquivo separado para revisão;
- logs usam o horário local do computador com o deslocamento UTC explícito;
- empacotamento alterado para diretório interno instalado, eliminando a
  extração `_MEI` temporária que causava a falha de `python313.dll`;
- autoteste do instalador continua obrigatório, agora usando as DLLs instaladas.

## 1.0.5 — 2026-07-28

- licença persistida em arquivo DPAPI vinculado ao computador, com backup
  criptografado e migração do JSON anterior;
- datas reais de início e vencimento incluídas na lease assinada pelo servidor;
- lista de processos limitada a executáveis cujo nome começa com `ProjectRF`;
- uma captura PktMon anterior é encerrada e seus filtros são removidos antes
  do novo início, com uma repetição controlada para o erro “já foi iniciado”;
- instalador executa o autoteste do programa instalado, salva `install.log` e
  não abre o aplicativo automaticamente ao finalizar.

## 1.0.4 — 2026-07-28

- o usuário escolhe o executável do jogo uma vez e a escolha fica salva;
- as portas TCP locais são descobertas automaticamente por processo, inclusive
  em reconexões, sem capturar toda a rede;
- suporte a até dois processos do jogo conectados ao mesmo tempo;
- capturas sem pacotes terminam normalmente e não geram exportações vazias;
- logs registram códigos sanitizados para falhas de captura e descoberta.

## 1.0.3 — 2026-07-28

- progresso visível durante consulta, download e verificação da atualização;
- o aplicativo salva o estado e encerra antes de o instalador substituir os arquivos;
- o instalador aguarda o fechamento de versões anteriores sem forçar o processo;
- atualização bloqueada durante captura ativa para evitar perda de dados;
- download parcial nunca é tratado como instalador verificado.

## 1.0.2 — 2026-07-28

- licença e logs persistidos na pasta comum do computador, com migração do formato anterior;
- recuperação de captura PktMon que permaneceu ativa após fechamento ou falha;
- arquivos ETL pendentes podem ser parados e analisados sem serem apagados;
- falha ao iniciar não substitui mais a referência da captura anterior;
- exportação permanece disponível mesmo se a licença não for reconhecida;
- botões de enviar, abrir a pasta e salvar uma cópia sanitizada do log no topo da aba Licença.

## 1.0.1 — 2026-07-28

- log técnico local com rotação automática e limite aproximado de 4 MB;
- remoção defensiva de licença, token, e-mail, IP, UUID e usuário do Windows;
- botão independente **Enviar log técnico** na aba Licença;
- upload somente após confirmação, pelo canal de diagnóstico já autenticado.

## 1.0.0 — 2026-07-28

- ativação e preferências preservadas durante atualizações;
- sessões isoladas a cada encerramento de captura;
- suporte a até dois personagens simultâneos por UID confirmado;
- Profile e nomes de personagens persistidos;
- JSON e CSV separados por personagem e sessão;
- nomes `Profile-Personagem-datahora-contador`;
- EXP bruta e percentual no level;
- aba Informações com tempo, level, EXP, créditos confirmados, contribuição,
  mercado, loot e kills estimadas por recompensa;
- diagnóstico separado sem payload, IP, flow, UID, personagem, chave ou licença;
- atualização estável/beta via release GitHub verificada por Ed25519 e SHA-256.
