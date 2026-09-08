# RF Next Companion — 2.0.0-beta.46

[Baixar instalador](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-agent-2.0.0-beta.46/RF-Next-Companion-Setup-2.0.0-beta.46.exe)

Correções de continuidade TCP em sessões longas, reconexão de clientes, limites
de filtros, recuperação/encerramento Pktmon/ETW e retomada de envio após SQLite
temporariamente ocupado. Falhas e leituras antigas ficam visíveis; logs limitados
por rotação. Preserva sessões e identidades durante recuperação da captura.
Nenhuma mudança no contrato de envio ou no receptor/site.

Regressão: 655 testes, sem falhas, dois skips opcionais. Replay privado de
equipamentos aprovado separadamente (12 testes). Inclui 18 testes específicos
de estabilidade com múltiplos clientes e ciclos de captura.
Autoteste empacotado e ensaio isolado de instalação, atualização e remoção OK.
Doze módulos empacotados conferidos contra o código validado.

**Windows 10 22H2 x64 ainda precisa de homologação física e sessão longa.** O
ensaio de instalação é no Windows 11. RAM é orçamento adaptativo, não teto rígido;
perdas nativas ETW não são mensuradas. Instalação interrompida, logon/UAC e
suspensão não foram homologados. O replay não substitui uma nova captura real.

Não instala drivers adicionais, não altera antivírus e não grava capturas brutas
em ETL/PCAP. Exige privilégios administrativos. O atualizador verifica manifesto
Ed25519, tamanho e SHA-256; a instalação exige confirmação do usuário.

Este projeto não utiliza Authenticode. Consulte UNSIGNED-NOTICE.txt e SHA256SUMS.txt.

Beta.45 permanece disponível para retorno manual. Restaurar o feed anterior
interrompe novas ofertas, mas não faz downgrade automático.
