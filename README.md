# RF Next Companion 2.0.0-beta.83

Diagnósticos automáticos de falhas de inicialização, interface, threads, captura, decodificação, projeção e entrega. O relatório inclui pilha de chamadas, causas, códigos do sistema, versões e estado técnico. Falhas nativas registradas são recuperadas na próxima abertura.

Envio HTTPS com assinatura da instalação vinculada, fila offline e novas tentativas. O relatório só sai da fila depois da confirmação do servidor. Relatórios repetidos são agrupados; o histórico no servidor é privado por conta.

Não são enviados senhas, chaves, tokens, pacotes do jogo, dados de personagens, variáveis locais ou dumps de memória. Valores arbitrários das exceções são omitidos; tipos, pilhas e códigos técnicos são conservados.

Windows 10/11 x64: o instalador escolhe o runtime adequado e inclui alternativa de captura NDIS/ETW para sistemas sem Pktmon compatível. Testado localmente em Windows 11; não houve acesso a uma máquina Windows 10 para homologação real.

Instalação pelo atualizador normal ou pelo instalador desta versão. Sem Authenticode por decisão do mantenedor; manifesto e procedência Ed25519, tamanho e SHA256 conferidos pelo atualizador.

Limites dos diagnósticos: 200 relatórios pendentes; repetição agrupada em janelas de dez minutos; tentativas com atraso de 15 segundos a 15 minutos; histórico do servidor de até 30 dias e 1.000 relatórios por instalação. Falhas anteriores ao início do Python e encerramentos forçados sem registro podem não produzir relatório.
