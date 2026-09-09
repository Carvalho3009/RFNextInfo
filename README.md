# RF Next Companion — 2.0.0-beta.47

[Baixar instalador](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-agent-2.0.0-beta.47/RF-Next-Companion-Setup-2.0.0-beta.47.exe)

Recupera colisões de sequência quando o receptor autenticado informa uma
recuperação segura, preservando IDs, conteúdo e horários. Conflitos de conteúdo
mantêm a fila e aparecem como conflito de sincronização, não site indisponível.
A correção correspondente do receptor foi publicada em 09/09/2026.

Inclui manutenção explícita para limpar eventos pendentes com backup verificado,
preservação de vínculo e validação da identidade da instalação. **Instalar ou
atualizar não apaga a fila automaticamente.** A manutenção exige orientação para
a instalação afetada e o programa fechado; não exclua o SQLite manualmente.

Regressão: 666 testes, sem falhas, dois skips opcionais. Receptor: 364 testes
sem falhas, 155 condicionais ignorados, incluindo integração real de colisão,
perda de ACK e reinício sem duplicação. Dezesseis testes dirigidos de perfil,
atualizador e recuperação repetidos antes da publicação.
Autoteste empacotado e ensaio isolado de instalação, atualização e remoção OK.
Quatorze módulos empacotados conferidos contra o código validado. A procedência
registra os hashes do source validado e explicita o commit de base, que não
representa sozinho as alterações ainda não commitadas do pacote.

**Windows 10 22H2 x64 ainda precisa de homologação física e sessão longa.** O
ensaio de instalação é no Windows 11. RAM é orçamento adaptativo, não teto rígido;
perdas nativas ETW não são mensuradas. Instalação interrompida, logon/UAC e
suspensão não foram homologados. O replay não substitui uma nova captura real.

Não instala drivers adicionais, não altera antivírus e não grava capturas brutas
em ETL/PCAP. Exige privilégios administrativos. O atualizador verifica manifesto
Ed25519, tamanho e SHA-256; a instalação exige confirmação do usuário.

Este projeto não utiliza Authenticode. Consulte UNSIGNED-NOTICE.txt e SHA256SUMS.txt.

Beta.46 permanece disponível para retorno manual. Restaurar o feed anterior
interrompe novas ofertas, mas não faz downgrade automático.
