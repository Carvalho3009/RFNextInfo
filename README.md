# RF Next Companion — 2.0.0-beta.43

- Adaptação de captura para Windows 10 22H2 x64 via Pktmon/ETW em tempo real.
- Mantém a captura nativa de streaming no Windows 11 e as correções da beta.42.
- Novas portas usam reinício controlado; falhas do consumidor deixam de aparecer como captura ativa.
- Diagnóstico inclui o backend e os motivos de bloqueio dos equipamentos.

Validação: 629 testes executados, sem falhas, 1 ignorado; 55 testes direcionados;
autoteste empacotado e ensaio automático de instalação aprovados.

**Windows 10 ainda precisa de validação em máquina real.** O ensaio de instalação
foi feito no Windows 11. O envio real de equipamentos também permanece em
investigação; não considerar o teste sintético como confirmação dessa correção.

Não instala drivers adicionais, não altera antivírus e não grava capturas brutas
em ETL/PCAP. Exige privilégios administrativos. O atualizador verifica manifesto
Ed25519, tamanho e SHA-256; a instalação exige confirmação do usuário.

Este projeto não utiliza Authenticode. Consulte UNSIGNED-NOTICE.txt e SHA256SUMS.txt.
