# Equipamentos — causa observada em 07/09/2026

Estado: correcao local implementada e validada por replay real, regressao e
receptor implantado usando banco temporario isolado. Ainda nao publicada.
Nenhuma publicacao, reinicio de captura ou alteracao do banco de producao.

## Evidencia do Agent em execucao

Consulta da API local por volta de 03:11 UTC:

- 3 `appear_player_prefix` aceitos, todos sem `equipment_refs`.
- Ultimo `appearance_tail_bytes`: 1012.
- 3 `player_profile_info` aceitos; 6 tentativas de projecao incluindo repeticoes.
- 2 tentativas sem personagem confirmado, 4 bloqueadas por `missing_appearance`.
- Ultimo perfil: 44 itens; 2 perfis pendentes; 0 snapshots de perfil projetados.
- Fila da ponte vazia, 0 erros da ponte; entrega ativa e 34155 eventos enviados.

O decoder da beta.43 publicada, antes desta alteracao, so extrai referencias
de equipamento para caudas de 988 ou 996 bytes. O formato observado de 1012
bytes retorna apenas o prefixo do personagem. O decoder canonico consultado
tambem nao suporta 1012 (aceita somente 988 nesse caminho).

Prova isolada executada com cabecalhos sinteticos, sem dados reais de pacotes:
988 e 996 produzem `equipment_refs`; 1012 nao produz. Essa prova demonstra a
condicao de exclusao, NAO determina onde ficam os campos no novo formato.

`_safe_parse` classifica 0x0403 como `player_profile_info`. Sua projecao exige
equipamentos correlacionados com o personagem confirmado. Sem referencias,
`project_many` retém o perfil e nao emite o snapshot completo. Repetir a
correlacao ou alterar a fila nao resolve a falta de extracao dos campos.

## Evidencia no receptor em producao

Consultas READ ONLY, restritas a instalacao/conta vinculada, timeout de 20 s.
O codigo da consulta de loadouts foi conferido dentro do conteiner ativo.

- Ultimos snapshots completos de inventario legado dos dois personagens:
  2026-08-28T09:48:14.280Z e 2026-08-28T10:07:50.994Z.
- Respectivamente 29 e 26 itens, `inventory_kind=''`, sem itens marcados como
  equipados. A data exibida nao comprova um loadout equipado corretamente.
- Desde 28/08 aparecem snapshots tipados como `equipment`, todos incompletos
  na agregacao historica consultada; nenhum completo desse tipo.
- Desde 02:22 UTC de 07/09, 1382 eventos de inventario estavam processados,
  e 2 pendentes naquele instante. Nao havia rejeicao nessa consulta.
- Nos 150 eventos recentes conferidos: 5 de equipment, `complete=false`, zero
  itens equipados; 145 de stackable, `complete=true`.

A consulta de loadout exige `complete=1`, prefere equipment e, na ausencia
dele, usa o inventario legado completo. Isso explica permanecer no dia 28.
Nao foi observado descarte de um novo loadout completo pelo site.

## Limites identificados antes da correcao

Os testes anteriores validavam referencias ja extraidas ou os layouts antigos;
nao cobriam a cauda de 1012 bytes observada em producao. As correcoes de ordem,
repeticao e preservacao de estado nao corrigiam essa condicao do decoder.

Era necessario validar os offsets do formato real de 1012 e cruzar suas
referencias com os UIDs de itens do perfil, para cada cliente. Nao simplesmente
adicionar 1012 a lista ou presumir que os 24 bytes extras ficam no fim.
Somente depois: teste de regressao com fixture fiel e sanitizada, validacao do
snapshot completo/equipado recebido pelo site e conferência dos dois clientes.
Nao atribuir a mesma causa a todo o periodo desde 28/08 sem captura historica.

## Correcao comprovada com captura real

Fonte local somente leitura: `K:\MCP\Karvalho\rf-next\tools\login-session-capture\captures\login-session-20260904-030442.pcap`.
SHA-256: `D77FC7FAA3240588796894069F70F35226CA23EEFB900BEE254542FC9C8883B1`.
O PCAP e seus identificadores nao foram copiados para o repositorio nem enviados
ao site. Apenas eventos sanitizados chegaram ao banco temporario do teste.

1. **Layouts ignorados**: essa captura contem dois prefixos de personagem,
   com caudas de 1004 e 1012 bytes. O bloco de 18 referencias comeca em
   `name_end + 839` nos dois casos. Os sufixos medem 67 e 75 bytes.
   Todos os 17 itens selecionados de cada personagem coincidem com o perfil
   recebido, tanto nos dois bytes iniciais quanto nos seis seguintes.
   UID publico e Biosuit tambem conferem com `world_info_prefix` da mesma conexao.
   O parser compartilhado agora aceita 988, 996, 1004 e 1012; tamanhos nao
   comprovados continuam sem referencias, sem busca heuristica por bytes.

2. **Perda de itens na projecao**: `_inventory_payloads` usava apenas o campo
   legado `inventory_slot` como chave. Ele se repete: 35/42 registros eram
   reduzidos a 12/13 antes de sair do Agent. O sufixo de seis bytes chamado
   `item_uid` tambem nao e suficiente: dois registros distintos do segundo
   perfil compartilham esse sufixo, mas possuem prefixos e item_index distintos.
   A referencia completa de oito bytes os distingue e coincide com os UIDs
   das mensagens reais 0x0501/0x0502 de troca de equipamento.

3. **Identidade completa preservada**: adicionado `item_uid_full` ao perfil e
   as referencias. Correlacao, estado do inventario e marcacao de equipado
   utilizam essa identidade completa. Campos legados foram mantidos para
   compatibilidade; nenhuma semantica nova foi atribuida ao campo antigo de slot.
   Os UIDs dos itens permanecem locais e nao entram no contrato publico.

4. **Contrato v1 mantido**: a chave `slot` enviada para equipment passa a ser
   o indice normalizado da linha dentro do snapshot, unica e deterministica
   para o mesmo conjunto. Nao e a posicao fisica no inventario do jogo.
   Isso evita tambem colisao na chave `(installation_id,snapshot_ref,slot)`
   do receptor. Stackable continua com o comportamento anterior. Nao foi
   necessaria alteracao do receptor nem migracao do banco.

## Testes desta correcao

- Antes do fix: replay real emitia **zero snapshots completos**; variantes
  1004/1012 falhavam, enquanto 988/996 passavam.
- Com apenas o layout corrigido: replay encontrou o segundo defeito e falhou
  com 12/13 registros em vez de 35/42. Usar somente seis bytes de UID ainda
  perdia um item, produzindo 35/41; a referencia completa elimina essa colisao.
- Depois: dois snapshots, **35/42 itens e 17 equipados em cada um**, com clientes
  e personagens distintos, nenhuma perda e nenhum perfil pendente.
- Testes permanentes partem de bytes de frames, incluindo remontagem TCP,
  formatos antigos/novos, tamanho desconhecido, identificadores abreviados
  iguais, troca de equipamento, deltas, exclusao, clientes e sessoes isolados.
- Replay privado opcional executado via `RFQOL_EQUIPMENT_PCAP`, apontando para
  a captura acima: `python -m unittest tests.test_equipment_delivery -v`.
  O teste nao acessa HTTP, a fila atual ou o banco de producao.
- Suite completa: **634 testes, OK, 1 skip**, em 83,899 s. O replay real estava
  habilitado. O skip e o caso opcional preexistente, nao o teste da captura.
- Self-test do decoder do Agent e do canonico: ambos OK.
- Receptor: executado o codigo instalado em `rf-qol-web-api-1` com
  `Store(caminho_temporario, database_url=None)`. Dois lotes validados pelo
  contrato e recebidos; dois eventos de ciclo e quatro privados processados;
  zero rejeicoes. `private_dashboard` retornou dois loadouts, 35/42 itens e
  17 equipados por personagem. O banco temporario foi removido ao fim.

## Entrega e gate restante

Branch local do Agent: `fix/equipment-appearance-tail-1012`, baseada na beta.43.
Mudanca localizada tambem aplicada ao decoder canonico sem substituir suas
outras alteracoes. Nenhum instalador foi gerado nesta etapa; atualizador segue
na beta.43. A captura atual continua com o binario anterior e nao recebe hot patch.

Proximo gate: empacotar e publicar a correcao quando autorizado; depois conferir
um novo snapshot da captura em uso no banco/site real. Replay com codigo do
receptor nao equivale a afirmar que o executavel instalado ja foi atualizado.

Custo real: unknown. Rollback: manter a beta.43 publicada; reverter apenas os
hunks desta correcao se necessario, preservando as demais alteracoes locais.
