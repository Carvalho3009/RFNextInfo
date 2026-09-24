# v38 — Contas simultâneas

Estado: execução autorizada pelo usuário e coordenada pelo agent-organizer. Perfis, importação, interface e dashboard implementados; validação/pacote descritos em VALIDACAO-v38.md. Permanecem pendentes o total diário comprovado, CP automático, layouts de equipamento não reconhecidos e validação visual/operacional real. Cadastro sem limite fixo; capacidade prática depende dos recursos do computador e do servidor, sem promessa de execução infinita.

## Experiência

Manter a identidade visual, o ajuste de fonte e as cinco áreas funcionais da v37, permitindo reorganizar seus layouts e acrescentando Dashboard como página inicial. Acrescentar seletor de conta pesquisável sempre visível, nome do perfil e estado do heartbeat. Cadastrar perfil com apelido e seus próprios arquivos de configuração/sessão, gerados pela importação do PCAP. Trocar o perfil visível mantém as outras contas trabalhando. Não criar uma aba por conta: a navegação deve continuar utilizável com muitos perfis.

As ações de Captura, Ranking, Mercado, Compras e Configuração operam apenas sobre a conta selecionada. Mostrar explicitamente a conta na confirmação de compra. Não iniciar todas as contas nem compras automaticamente ao abrir. Uma conta pode consultar enquanto outra mantém heartbeat ou executa sua própria consulta.

## Repaginação visual coordenada pelo patrão

Proposta elaborada pelo `agent-organizer`, depois implementada na etapa autorizada. Com limite de quatro threads, o organizador assumiu a frente visual; não houve revisão independente pelos especialistas visuais previstos.

- Direção: referência de dashboard escuro fornecida por Carlos, fundo cinza, superfícies com contraste discreto, texto branco e Arial Rounded MT com tamanho ajustável. Manter Segoe UI como alternativa quando a fonte não estiver instalada. Não criar gráficos ou indicadores decorativos sem dados úteis.
- Estrutura: navegação lateral com Dashboard, Captura, Ranking, Mercado, Compras e Configuração. Cabeçalho permanente com conta selecionada, personagem identificado, estado da conexão e seletor de contas. As ações devem deixar explícita a conta afetada.
- Muitas contas: seletor pesquisável com apelido, personagem e estado; cadastro e importação acessíveis nesse seletor. Lista com rolagem, sem abas ou cartões individuais por conta. Trocar a conta exibida preserva operações e resultados das demais.
- Dashboard: bloco de identidade e localização; indicadores de diamantes, nível e CP; classe, Biosuit e Rover agrupados; missões realizadas/10; lista das quatro dungeons com tempos. Cada grupo mostra atualização e estados “Não observado” ou “Último valor conhecido”, sem transformar informação desconhecida em zero.
- Áreas existentes: Captura reúne controles e progresso por operação; Mercado preserva produto → refino → ofertas com espaço para leitura; Compras destaca conta compradora, origem da lista, quantidade, preço e resultado antes da execução. Diagnóstico continua em Configuração.
- Estados: diferenciar conexão, heartbeat confirmado, operação em andamento, espera pelo próximo ciclo, erro e cancelamento usando texto além de cor. Erros de uma conta não encobrem as demais. Controles indisponíveis explicam o motivo.

Aceite visual: navegação por teclado e foco visível; fonte ajustável sem cortar comandos; rolagem em listas e tabelas extensas; contexto da conta sempre visível; estados vazios e antigos compreensíveis. Comparar hierarquia, espaçamento e legibilidade com a referência, sem copiar indicadores fictícios. A avaliação visual manual deve ser registrada separadamente dos testes simulados.

Coordenação futura: `agent-organizer` consolida escopos e dependências → `ui-designer` define composição e estados com dados representativos → responsável Python adapta `desktop_shell.py` após estabilizar o estado por perfil → `accessibility-tester` e `anti-ui-slop-reviewer` revisam a entrega. Aguardar cada dependência; especialistas não editam o shell simultaneamente. A definição visual pode avançar em paralelo ao núcleo, mas sua integração depende do isolamento de contas e do roteamento de eventos já testados.

## Isolamento obrigatório

- Cada perfil tem identificador local estável, credencial, configuração, HeartbeatWorker, cancelamentos, agendamentos, resultados, histórico e fila de compras próprios.
- Guardar estado em `accounts/<profile_id>/`; nomes visíveis não viram caminhos. A base de itens pode ser compartilhada somente para leitura e a aparência continua global.
- Eventos carregam profile_id e identificador da execução desde sua origem. Eventos atrasados nunca atualizam a conta errada. Trocar a seleção não altera configuração de worker em andamento.
- Parar uma conta não para outra. Editar sessão de conta ativa exige primeiro encerrar as operações daquela conta. Fechar o programa encerra todos os workers com o procedimento existente, sem perder compras incertas ou uploads pendentes.
- Identificar conta pelo account_id validado da sessão, quando disponível; bloquear dois perfis ativos com a mesma identidade. Não inferir identidade pelo apelido nem pelo personagem.
- Compras utilizam exclusivamente o heartbeat e os resultados do perfil de origem. Não mover proposta, reserva ou resultado confirmado entre contas.

## Configuração automática pela captura PCAP

Fluxo: Adicionar conta → importar PCAP → identificar conta e sessão → apresentar dados detectados → salvar perfil. Reutilizar a remontagem TCP e o decoder existentes; portas isoladas ou a ordem dos pacotes não bastam para associar sessões. Não criar novo capturador nesta etapa: a entrada é o arquivo produzido pela captura existente.

Extrair automaticamente:

- IP e porta remotos do login host, a partir da conexão de autenticação identificada (serviço atual 12000).
- IP e porta remotos do game host, a partir da conexão de jogo correspondente (serviço atual 12020).
- World ID efetivamente selecionado naquela sessão, confrontando requisição/resposta quando presentes. Não escolher simplesmente o primeiro mundo anunciado na lista do servidor.
- Identidade da conta, credenciais e templates exigidos pelos fluxos existentes, preservando valores reais e campos desconhecidos. Handles gerados durante a nova conexão continuam dinâmicos conforme o executor atual; não copiar esses valores como constantes.

Se houver várias contas, reconexões ou sessões no mesmo arquivo, mostrar candidatos agrupados com conta, horário e endpoints para seleção. Não combinar JWT de uma sessão com game host/world de outra. Importar captura mais recente de uma conta já cadastrada atualiza esse perfil com confirmação da associação, sem duplicar a conta nem apagar seu histórico.

Captura incompleta: informar exatamente o que não foi encontrado; permitir revisão manual identificada como tal. Não usar placeholders, localhost ou world_id=1 como substitutos silenciosos. Guardar origem por campo (arquivo, conexão, horário e mensagem) para diagnóstico. Importação não inicia autenticação, heartbeat, coleta nem compra; a validade atual da credencial só pode ser confirmada na conexão posterior.

Evidência local: `preparar_teste_do_dump.py` hoje exige `--auth-host` e `--game-host` e usa world ID padrão 1; essa rotina deve ser reaproveitada e corrigida para consumir a sessão selecionada. A descoberta automática de PCAP ainda não está implementada nesse gerador.

## Dashboard por conta

Mostrar o personagem selecionado e o horário da última atualização. Se uma conta apresentar vários personagens, identificar cada character_uid e não fundir seus dados. Os seguintes campos fazem parte do escopo:

| Área | Dados a mostrar | Regra de interpretação |
| --- | --- | --- |
| Personagem | Nome, character_uid e saldo de diamantes | Confirmar identidade do personagem da conta antes de associar saldo |
| Desenvolvimento | Classe, Biosuit, Rover, level e CP | Exibir valores e nomes validados; manter ID quando o catálogo não resolver o nome |
| Missões diárias | Realizadas, limite diário 10 e saldo de conclusões restantes | Contador do total diário, não contador de conclusões instantâneas; saldo não prova que há missões oferecidas |
| Dungeons limitadas | Android Junkyard, Secret Nemesis Base, Public Mining Field e Exclusive Mining Field, com tempo restante por dungeon | Confirmar se o valor é tempo disponível, consumido ou prazo; não aplicar uma fórmula comum sem evidência |
| Localização | Mapa/região e coordenadas quando decodificadas | World ID não é localização; nunca usar posição de outro jogador |

Usar os snapshots da importação e as mensagens recebidas pela própria sessão para atualizar o painel. Heartbeat confirmado não significa que saldo, missões ou localização foram atualizados. Cada grupo conserva sua própria fonte e horário; mostrar “Não observado” para campo ausente e “Último valor conhecido” após desconexão. Zero somente quando recebido ou derivado por regra validada. Não iniciar um relógio de dungeon que diminui fora dela sem comprovar essa regra.

O painel não acrescenta mensagens de consulta desconhecidas ao protocolo: se um campo precisar de requisição específica, identificar e validar essa mensagem antes de implementá-la. Não depender de consultar rankings de outros jogadores para preencher os dados privados da conta.

### Evidência e trabalho de decoder

Na inspeção atual, `tools/events-db/rfnext_frame_decode.py` contém campos world_id, prefixos de identificação e o prefixo 0x0305 com character_uid, character_name, level e diamonds. Isso é um ponto de partida, não comprovação de saldo atual da própria conta: a mensagem de aparecimento também pode referir-se a outro personagem.

O parser de personagem do cliente atualmente extrai result_code e character_uid de 0x0202 e preserva a cauda desconhecida. Antes do dashboard, localizar a versão canônica mais completa do decoder e validar os campos restantes (classe, Biosuit, Rover, CP, contador diário, tempos e localização) com capturas. A ausência desses campos nos arquivos inspecionados não prova ausência no protocolo. Registrar opcode, direção, estrutura, unidade, vínculo ao personagem e evidência de cada campo; campos incertos não recebem rótulos definitivos.

## Reutilização do código

`DesktopApp` atualmente concentra um único conjunto de estado. Separar esse estado por perfil e manter uma única interface Tk. Reutilizar `complete.HeartbeatWorker`, os executores de consulta, `PurchaseList` e o protocolo atual. Não alterar opcodes ou fórmulas de heartbeat nesta mudança.

Remover dependência do caminho global de `purchase-list.json`, parametrizando seu diretório pelo perfil. Preservar a lógica de não repetir compras incertas. Não criar uma janela Tk independente por conta nem copiar o programa inteiro por perfil.

## Companion e lista do site

Conta de jogo e instalação vinculada no Companion são conceitos distintos. Preservar o vínculo existente e não clonar identidade/contadores de upload em bancos independentes. Para perfis do mesmo proprietário, reutilizar a fila existente e sua serialização `_UPLOAD_LOCK`; não alterar o contrato publicado nesta etapa. Vínculos diferentes mantêm diretórios próprios, explicitamente selecionados.

Consultar a mesma lista do site em duas contas não autoriza executar os mesmos itens duas vezes. Antes de habilitar execução simultânea dessa lista compartilhada, definir reserva única por proprietário/shopping_id entre perfis. Até isso existir, permitir somente um perfil executor para uma mesma lista do site. Listas locais permanecem independentes. O backend de listas continua fora deste escopo.

## Migração

Importar os dados atuais como primeiro perfil, preservando cópia dos arquivos originais e o vínculo Companion. A migração deve ser idempotente, com gravação atômica e sem limpar histórico. Não migrar uma compra em andamento como preparada. O modo de uma conta precisa continuar funcionando como na v37.

## Ordem e critérios de entrega

1. Persistência dos perfis, migração e resolução dos caminhos.
2. Estado de execução por perfil e roteamento de eventos, sem mudar o protocolo.
3. Importação PCAP com seleção de sessão e configuração automática de hosts/world ID; testar captura completa, parcial, retransmissão, reconexão e múltiplas contas.
4. Repaginação visual coordenada pelo `agent-organizer`, conforme seção própria: composição pelo `ui-designer`, seletor de conta e adaptação das áreas existentes; indicação permanente da conta compradora. Integrar somente após validar o isolamento por perfil.
5. Inventário e validação dos campos do decoder, depois Dashboard com atualização e origem por campo.
6. Cancelamento, encerramento, upload e reserva da lista do site entre perfis.
7. Regressão da v37 e testes de contas simultâneas com executores simulados: parar A não para B; evento de A com B selecionada; token/heartbeat correto por compra; arquivo/lista/resultados não se misturam; sessão duplicada bloqueada; reinício com compra incerta; vínculo existente preservado. Testar identidade de jogador, missões totais versus instantâneas, campos ausentes, valores antigos e unidades de dungeon.
8. Testar cadastro sem teto artificial e concorrência em volumes crescentes, registrando memória, responsividade e encerramento. Preparar ZIP somente após implementar e validar o escopo. Teste real de sessões e avaliação visual permanecem separados dos testes simulados; não realizar compras reais como teste de desenvolvimento.

Entrega v38: implementação e pacote no canal GitHub atual, com limites documentados. A v37 permanece como referência anterior. Não considerar os campos de dados pendentes como concluídos somente porque o dashboard já possui espaço para eles.
