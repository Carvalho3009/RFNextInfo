# RF Next Companion 2.0.0-beta.45

Sequencia de atualizacao: 55. Publicada no canal beta em 07/09/2026 UTC,
com autorizacao do owner.

- Corrige a leitura da resposta do Pktmon no caminho ETW do Windows 10:
  preserva bytes e reconhece UTF-8 e as paginas OEM/ANSI do proprio Windows.
- O mesmo parser atende a verificacao inicial e a espera pelo stream ativo.
- Captura ocupada, estado desconhecido ou interpretacoes conflitantes continuam
  bloqueados; nenhuma captura de terceiros e encerrada.
- Preserva a correcao de equipamentos da beta.44 e o transporte atual. Nao exige
  alteracao do receptor/site e nao modifica a captura streaming do Windows 11.

Validacao anterior ao empacotamento: 637 testes, sem falhas, 1 skip opcional;
replay privado de equipamentos habilitado. Inclui subprocesso real oculto com
texto fixo PT/EN, inicio/encerramento ETW simulados e testes com `python -X utf8`.
Nao equivale a teste fisico do instalador no Windows 10 afetado.

## Publicacao validada

- Regressao do pacote: 637 testes em 78,777 s, sem falhas, 1 skip opcional;
  replay privado de equipamentos habilitado.
- Self-test empacotado e ensaio isolado de instalacao, atualizacao e remocao OK.
- Cinco modulos do executavel comparados ao codigo validado; nove casos de
  estado executados com o parser extraido do pacote. Codecs necessarios presentes.
- Download publico completo, tamanho, hash e ambas as assinaturas verificados.
- Atualizador oferece beta.45 para sequencias 51 a 54, sem repetir para 55.
- Codigo: `7331f806714b2f0f899f7966d533d1e1d362cc0d`.
- Artefato: `81664ba274f773d5688b29f1fb6b00996598ce5d`.
- Canal: `52d0e7138175206ead8e9bb1f92c595f3551629d`.
- Instalador: 35.740.092 bytes; SHA-256
  `95bfc65a87f4789f0757a78c93f148b51829b8735c87f851c7ff3acce0b5441d`.

[Instalador publico](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-agent-2.0.0-beta.45/RF-Next-Companion-Setup-2.0.0-beta.45.exe)

Nenhuma instalacao em uso foi atualizada ou interrompida. Nenhum receptor alterado.
Falta validar a captura apos instalar a atualizacao no Windows 10 afetado.
Sem Authenticode, UPX, exclusoes ou bypass de antivirus.

Rollback: preservar artefato e manifesto beta.44. Restaurar o feed anterior
suspende novas ofertas, mas nao rebaixa instalacoes ja atualizadas.
Custo real: unknown. Captura em uso nao deve ser interrompida.
