# beta.42 — teste local de equipamentos (nao publicada)

## Estado real

A beta.41 em uso recebeu dois perfis, mas nao os projetou. O servidor recebeu
14 snapshots de equipamento apos a atualizacao, todos sem itens equipados.
O envio estava ativo. Os contadores existentes nao informam a causa do descarte;
nao ha evidencia suficiente para atribuir essa falha ao decoder, UID ou ordem.

## Alteracao

- Impede que uma correlacao explicitamente incompleta apague os equipamentos
  anteriormente confirmados. O teste de regressao falha sem essa protecao.
- Acrescenta `capture_bridge.equipment_diagnostics` a saude da API local e ao
  diagnostico exportado: motivos do bloqueio, quantidades de itens/referencias,
  tamanho da cauda da aparicao e numero de perfis pendentes. Sem nomes, UIDs,
  enderecos, tokens ou conteudo de pacotes. Chaves fixas e memoria limitada.
- Nao altera decoder, contrato do site, regra de confirmacao ou fila existente.

## Validacao e proximo passo

Regressao de codigo: 617 testes, sem falhas, 1 ignorado. O instalador de teste
tambem deve passar pelo autoteste empacotado e pelo ensaio instalado antes de
ser entregue. O build-evidence.json acompanha esse resultado.

Depois de instalar, aguardar os eventos do jogo e exportar o diagnostico. Se
`profile_attempts` nao aumentar, sera necessario provocar uma nova leitura no
cliente; instalar nao recupera os perfis que ficaram apenas na memoria anterior.
Nao limpar a fila nem reiniciar o jogo automaticamente. A confirmacao final
exige snapshots reais com equipamentos corretos no servidor para cada cliente.

Publicacao no atualizador pendente de autorizacao e validacao real. Nao afirmar
que o bloqueio observado na beta.41 foi resolvido apenas pelo teste sintetico.
