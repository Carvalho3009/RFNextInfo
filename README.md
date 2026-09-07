# RF Next Companion — 2.0.0-beta.44

- Corrige a leitura dos formatos de equipamento ignorados de 1004 e 1012 bytes.
- Usa a referência completa dos itens, evitando colisões e perda de equipamentos.
- Exporta todos os registros com índices únicos, sem sobrescrita no site.
- Mantém as funcionalidades da beta.43 e o caminho Pktmon/ETW para Windows 10.

Validação funcional: captura real com dois personagens gerou snapshots de 35 e
42 itens, com 17 equipados por personagem. O código implantado do receptor aceitou
e exibiu os dois loadouts em banco temporário isolado, sem rejeições.

Regressão: 634 testes executados, sem falhas, 1 ignorado; replay real habilitado.
Autoteste empacotado e ensaio automático de instalação aprovados. Decoder,
projeção e versão dentro do executável conferidos contra o código validado.

**Windows 10 ainda precisa de validação em máquina real.** O ensaio de instalação
é feito no Windows 11. O replay não substitui a conferência de uma captura nova
em produção após o usuário instalar esta atualização.

Não instala drivers adicionais, não altera antivírus e não grava capturas brutas
em ETL/PCAP. Exige privilégios administrativos. O atualizador verifica manifesto
Ed25519, tamanho e SHA-256; a instalação exige confirmação do usuário.

Este projeto não utiliza Authenticode. Consulte UNSIGNED-NOTICE.txt e SHA256SUMS.txt.
