# RF Next Companion — 2.0.0-beta.45

- Corrige a leitura do estado do Pktmon em português no Windows 10.
- Preserva os bytes da resposta e reconhece UTF-8 e as páginas OEM/ANSI do Windows.
- Mantém o bloqueio quando a captura está ocupada ou o estado é desconhecido.
- Preserva as correções de equipamentos da beta.44 e o caminho de streaming do Windows 11.

Validação funcional: testes com subprocesso oculto imprimindo apenas frases PT/EN,
controle ETW simulado e replay privado de equipamentos com dois personagens.
Nenhuma mudança no contrato de envio ou no receptor/site.

Regressão: 637 testes executados, sem falhas, 1 ignorado; replay real habilitado.
Autoteste empacotado e ensaio isolado de instalação, atualização e remoção OK.
Cinco módulos empacotados conferidos contra o código validado; nove casos de
estado executados usando o parser extraído do executável.

**Windows 10 ainda precisa de validação em máquina real.** O ensaio de instalação
é feito no Windows 11. O replay não substitui a conferência de uma captura nova
em produção após o usuário instalar esta atualização.

Não instala drivers adicionais, não altera antivírus e não grava capturas brutas
em ETL/PCAP. Exige privilégios administrativos. O atualizador verifica manifesto
Ed25519, tamanho e SHA-256; a instalação exige confirmação do usuário.

Este projeto não utiliza Authenticode. Consulte UNSIGNED-NOTICE.txt e SHA256SUMS.txt.
