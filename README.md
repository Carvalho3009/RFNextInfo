# RF Next Companion — 2.0.0-beta.52

Sequência 62 do canal beta. Instalador, manifesto e procedência verificados; manifesto e procedência assinados com Ed25519. Não usa Authenticode, conforme o canal existente.

Rotação lógica de sessão a cada seis horas, preservando captura e fila; recuperação de rotação interrompida, proteção contra conclusão atrasada após parar ou iniciar outra captura, prioridade de eventos de chefe e localização confirmada. Recibos do Companion preservam rejeições explícitas e são aplicados atomicamente à fila local.

Validação: 713 testes, 711 aprovados e dois ignorados; autoteste empacotado e instalação temporária passaram; 33 módulos e cinco dados correspondem às fontes verificadas. Sem homologação física no Windows 10 ou captura em jogo real nesta entrega.

A atualização preserva os dados do usuário. Não apague a pasta LocalAppData do Agent nem limpe a fila para atualizar. Captura não ocorre durante o intervalo em que o programa está fechado para instalação. A versão anterior permanece disponível; voltar o canal não força downgrade automático.
