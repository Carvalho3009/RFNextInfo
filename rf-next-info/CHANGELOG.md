# Changelog

## 1.0.11 — instalação manual

- Desativa temporariamente a aba, atualização e sincronização do Banco PvP,
  preservando os dados locais e mantendo o Monitor PvP ativo.
- Permite exibir a vida do alvo selecionado na rota confirmada de um cliente
  mesmo antes de o personagem local ser reconhecido, sem misturar clientes ou
  criar monitores provisórios sem seleção de alvo.
- Mantém somente uma rota ativa no Monitor PvP: ao ligar outro cliente, o PvP
  anterior é desligado sem afetar os monitores PvE e Boss.

## 1.0.10 — instalação manual

- Mantém o log técnico detalhado sempre ativo, preservando a sanitização de
  licenças, tokens, endereços e conteúdo bruto de pacotes.
- Aceita portas secundárias do próprio processo do ProjectRF quando o ExitLag
  redireciona a conexão e associa o fluxo PvP ao cliente pela UID confirmada.
- Não inclui conexões pertencentes ao serviço do ExitLag na captura.

## 1.0.9 — instalação manual

- Corrige o envio automático do Ranking de EXP para respeitar o contrato Top
  100 do site, mesmo quando o servidor do jogo entrega 300 posições no pacote.
- Mantém capturas parciais ou conflitantes pendentes e envia somente posições
  únicas de um mesmo escopo e ciclo.

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
