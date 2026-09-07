# RF Next Companion 2.0.0-beta.45

Sequencia de atualizacao: 55. Publicacao autorizada; em preparacao.

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

Release exige regressao, self-test empacotado, ensaio isolado do instalador,
verificacao dos modulos empacotados, hash publico e assinaturas Ed25519.
Sem Authenticode, UPX, exclusoes ou bypass de antivirus.

Rollback: preservar artefato e manifesto beta.44. Restaurar o feed anterior
suspende novas ofertas, mas nao rebaixa instalacoes ja atualizadas.
Custo real: unknown. Captura em uso nao deve ser interrompida.
