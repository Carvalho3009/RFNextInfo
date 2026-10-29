# RF Next Companion beta.62

Corrige o encerramento da captura própria ao sair e preserva o controlador quando a parada falha, permitindo nova tentativa. O X mantém o Companion na bandeja; Sair encerra o programa.

Adiciona Forçar limpeza de filtros nos erros do Pktmon, com confirmação. Remove apenas filtros antigos do Companion, com Pktmon parado e processos responsáveis encerrados. Capturas ativas, filtros externos e estados desconhecidos bloqueiam a limpeza. A captura automática é desativada antes da limpeza; a leitura pode ser iniciada depois pelo usuário.

767 testes: 765 aprovados e 2 ignorados. Autoteste empacotado e instalação isolada aprovados; manifesto e procedência Ed25519. Sem teste de captura real ou ações no jogo. Encerramento forçado pelo sistema pode impedir a limpeza normal. Instalador sem Authenticode, conforme política do produto.
