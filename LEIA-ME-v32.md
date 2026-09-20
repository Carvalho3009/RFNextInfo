# RF Next — v32

Correção da regressão da v31: a conexão usada pelo ranking agora inicializa o personagem com 0x0201 e exige a resposta válida 0x0202 antes de requisitar EXP e as três facções. O mesmo caminho atende os botões de ranking individual/contínuo e a etapa de ranking da consulta completa.

Se todos os rankings falharem, o resultado é failed. Se houver dados parciais, é incomplete. A consulta completa não apresenta sucesso total quando o mercado conclui mas faltam rankings. Ofertas disponíveis ainda seguem para o envio.

Estados de encerramento dos workers são conservados separadamente dos quadros do log visual e incluídos na exportação, com horário. Esse histórico também é limitado (1.000 eventos); não é uma captura ilimitada.

Mercado, ranking e consulta completa mantêm seus controles independentes da v31. O servidor do Companion continua https://apirf.karvalho.dev.br. O suporte de até 300 registros não garante que o jogo retorne 300 por facção.

Extraia o ZIP na pasta do cliente preservando config.json, session.json, base de itens e companion-state. Abra run-client.bat e confirme v32 no título.

Limitação: esta alteração corrige a inicialização omitida e o resultado falso. A coexistência das conexões autenticadas e a persistência do heartbeat dependem do teste com o servidor real; não foram declaradas resolvidas.
