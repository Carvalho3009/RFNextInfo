# RF QOL 2.0 — Perfil de homologação

Estado: instalador de homologação gerado em 20 ago 2026.

## Identidade

- perfil: `staging`;
- versão: `2.0.0-rc1`;
- sequência: `10`;
- título visível: `RF QOL — 2.0.0-rc1 (Homologação)`;
- instância Windows: `RFQOL.Staging.App`.

## Isolamento

- licenciamento: `http://127.0.0.1:8788`;
- chave aceita: somente a chave pública `lease-v3-staging-2026-01`, além da
  chave pública v2 preservada para leitura compatível;
- chave privada: permanece exclusivamente no emissor de staging;
- estado protegido da máquina: `ProgramData\Karvalho\RF QOL Staging`;
- integração remota com o site: liberada somente para validar o token do
  Profile e enviar capturas do Mercado;
- atualização automática: desativada;
- build de release: recusado pelo perfil;
- instalador: permitido somente pela opção explícita de homologação, com pasta,
  registro, atalhos e desinstalador separados da instalação RF QOL normal.

O estado de licença da linha 1.x não é lido, alterado nem removido. O perfil de
homologação pode executar em paralelo porque usa nome de instância diferente.

## Executável candidato

O instalador isolado atual é
`dist\RF QOL Setup 2.0.0-rc1 Homologacao.exe`, com SHA-256
`A4E91C9EBAC4191CF866B0BCAD3718CEE40F93DD2FCB902B58E621940A20122E`.
Ele instala em `Program Files\Karvalho\RF QOL Staging` e usa registro e atalhos
próprios, sem substituir a linha RF QOL normal. O build passou 393 testes, o
autoteste do executável empacotado, `pip check`, SBOM e inspeção dos metadados.
O instalador permanece `NotSigned`.

O ensaio automático isolado também passou: compilou um instalador de smoke,
instalou silenciosamente em pasta temporária, confirmou `self_test=0`,
desinstalou e verificou que o executável instalado foi removido. A instância de
homologação que já estava aberta permaneceu em execução e não foi alterada.

O pacote portátil foi gerado em
`dist\RF QOL 2.0.0-rc1 Homologacao visual-v21.zip`. O fluxo executou 371 testes,
o autoteste do binário empacotado, `pip check`, SBOM e procedência local marcada
com `build_profile=staging`. O executável interno possui SHA-256
`DA07D0FBEBDEF324994BF60C61B9D0D5723089AE9530E75931342930801EFEC4`.
O ZIP possui SHA-256
`2DA3D7EA397D55A4A2F992A791B5DEC6AD06BD4D91764E7D9230A6C13B03BEF5`.

O candidato v21 calibra a projeção viva do High-Orbit Launch Base. A escala e
a origem foram obtidas comparando 52 aparições vivas dos NPCs 359101, 359102,
359103 e 359190 com seus spawns estáticos oficiais. A coordenada observada
`1183, 684` deixa de ser tratada como coordenada de mundo bruta e passa pela
transformação própria do mapa; o mesmo contrato é aplicado aos jogadores
próximos e à planta compartilhada pelo MapIndex 644. O gerador também lê dos
assets os limites e a escala oficiais de cada planta, mantendo fallback quando
essa fonte não estiver disponível.

O candidato v20 já havia corrigido a planta ausente quando o mapa foi definido pelo
fallback manual. O fallback passa a transportar o MapIndex da planta; escolhas
anteriores que guardavam somente nome e região são resolvidas automaticamente.
O autoteste do executável e o smoke do ZIP agora carregam especificamente o
asset `639.webp` do Android Junkyard 9F e falham se a planta não abrir.

O site de produção aceita o contrato anterior de licença v2 sem alteração e
encaminha somente leases v3 deste Mercado ao emissor isolado de homologação.
O aplicativo permite validar o token do Profile e habilita apenas o botão e o
envio automático de Mercado; as demais modalidades de envio permanecem
bloqueadas pelo perfil. O deploy foi feito sobre a imagem que já estava em
execução, trocando somente o servidor e a configuração necessários para esse
contrato, com imagem de rollback e backup SQLite íntegro preservados.

Neste candidato, as portas locais efêmeras continuam identificando o cliente,
mas não são acumuladas como filtros permanentes do PktMon. Isso evita esgotar o
limite de conexões durante execuções longas e interromper a coleta de EXP e
abates. A gravação de uma nova subsessão também prioriza a sessão de captura
realmente ativa, mesmo antes da próxima atualização visual.

Foi emitida e ativada uma licença RFQ temporária somente no emissor de staging,
com as sete features da 2.0. A chave de ativação temporária foi removida após o
uso e não foi gravada no repositório nem incluída no pacote. A lease local pode
ser revalidada em cada abertura, limitada a sete dias por emissão.

A interface da Visão geral foi portada para o mockup 2.0 e comparada por
renderização Qt automática em 1600 x 1000, registrada em
`docs/mockups/rf-qol-2.0-overview-v4.png` e
`docs/mockups/rf-qol-2.0-exp-ranking-v1.png`. O gate visual manual do owner
ainda não foi executado.

O seletor de clientes pergunta a origem antes de adicionar, usa vagas distintas
para PC e emulador e permite excluir clientes adicionados somente da interface.
Sessões e dados permanecem preservados. A origem externa continua bloqueada até
a implementação do pareamento e da API LAN.

As ações de captura usam ícones vetoriais próprios, independentes do tema do
Windows: verde para iniciar, ouro para pausar, coral para encerrar e coral com
risco para encerrar sem ler. Ações indisponíveis usam somente cinza neutro.

O badge de status usa `Teleportando > PvP > Farm > Ocioso`. Farm exige dano ou
abate confirmado de mob nos últimos 30 segundos; EXP e seleção de alvo isoladas
não ativam Farm. A leitura de estado usa a captura ativa mesmo quando o cartão
do Monitor PvE estiver desligado. PvP exige dano real causado ou recebido, e
Boss permanece como sinal independente de proximidade. A aba Mapa abre uma lista pesquisável para
selecionar o nome manual por cliente apenas como fallback quando o automático
não reconhecer o mapa. A leitura automática permanece ativa e assume sem
intervenção assim que resolver o nome.

O mapa oficial de Albern Crater foi incluído como recorte local para os IDs 751
e 754, que compartilham a mesma área visual. O ID reconhecido automaticamente é
preservado, enquanto a lista manual agrupa os dois IDs em uma única opção. A
Visão geral projeta a posição local, os jogadores próximos e seus nomes sobre o
recorte; os nomes também permanecem disponíveis em texto no cartão.

Os drops recentes mostram o ícone do item e aplicam as cores do catálogo por
raridade: Comum, Incomum, Raro, Épico e Lendário; itens sem grade confirmada
permanecem em cinza neutro.

Os cartões **Sessão atual** e **Subsessão ativa** são independentes na Visão
geral e permanecem visíveis ao mesmo tempo. O cartão de subsessão oferece o menu
**Informações**, com as mesmas opções de campos disponíveis como colunas no
histórico de subsessões. O Top 100 mostra Nível
e EXP %, derivados da EXP total pela curva oficial 1.28.5 porque esses dois
campos não fazem parte do pacote de ranking.

**Subsessões** agora é uma página própria na navegação, separada de **Sessões**.
A página **Drops** também é independente e o botão da Visão geral abre essa
área diretamente. Ela mostra os itens confirmados da sessão com ícone,
personagem, cliente, quantidade, raridade, horário e idade do registro, além de
busca, filtros e paginação. A projeção permanece limitada aos 1.000 eventos mais
recentes da sessão e renderiza no máximo 100 linhas por página para proteger a
memória.

A barra lateral rolável aplica explicitamente o fundo escuro ao contêiner, ao
espaço entre os botões, à área livre e à barra de rolagem. Isso corrige o fundo
claro herdado da paleta do Windows que apareceu no candidato v13. Um teste de
renderização offscreen verifica os pixels dessas áreas para impedir regressão.

Em **Sessões > Histórico e subsessões > Nova subsessão**, o botão **Buscar
localização e mobs agora** preenche o rascunho com o contexto recente do cliente
selecionado, sem criar nem iniciar a subsessão. A opção de preenchimento contínuo
por proximidade permanece separada.

A Visão geral volta a ocupar o antigo espaço de alvo com **Mobs próximos**.
A tabela agrupa aparições repetidas e mostra somente nome, nível e vida máxima
do cliente selecionado; alvo, vida atual, percentual e DPS não são exibidos.

## Fora deste gate

- chave definitiva de produção;
- demais integrações de envio ao site;
- publicação, deploy, cutover ou release;
- ensaios manuais, visuais, de dois clientes e de 10 horas.

## Rollback

O rollback do candidato consiste em descartar a pasta/ZIP portátil e restaurar
o código anterior no worktree. Se o owner também decidir remover o estado
`RF QOL Staging`, isso não afeta a instalação RF QOL normal, pois os diretórios
e a instância Windows permanecem separados.
