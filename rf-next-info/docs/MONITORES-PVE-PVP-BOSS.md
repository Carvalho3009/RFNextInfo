# Monitores PvE, PvP e Boss — 1.28.5

## Fluxo implementado

O Pktmon entrega os pacotes a um único stream. O decoder reagrupa TCP em RAM,
descarta `0x0101` antes de criar eventos e distribui somente estruturas já
decodificadas aos monitores. Os monitores podem continuar ligados sem a
captura histórica; nesse modo nenhum ETL/PCAP é criado.

PvE, PvP e Boss possuem relógios independentes. Alterar a frequência muda
somente a atualização da interface, não reinicia o Pktmon nem cria outra
captura.

O overlay PvP usa exclusivamente o cliente selecionado na aba do Monitor PvP.
Ele mostra somente o alvo atual confirmado por `0x0609`, `0x0601` ou pelo alvo
principal do resultado de combate e limpa a linha após três segundos sem nova
confirmação. Jogadores próximos e os demais clientes permanecem apenas nas
telas completas dos monitores.

## Evidência usada

- `0x0305`: jogadores visíveis, UID de combate, `character_uid`, nome,
  Biosuit/Rover e HP.
- `0x0307` no layout de lista: mobs visíveis, `npc_index`, HP, posição e
  `guild_id` do registro de unidade.
- `0x0311`: atualização de HP/FP.
- `0x0316`: unidade morta.
- `0x0602` e `0x060D`: resultado de habilidade/ataque, dano e HP final.
- `0x0609`: seleção de alvo enviada pelo cliente. O UID de 4 bytes coincidiu
  com o alvo principal dos pedidos/resultados seguintes em 100% dos 90 eventos
  correlacionados na captura real usada para esta correção.
- `0x0601`: pedido de habilidade enviado pelo cliente; o terceiro campo de
  32 bits confirmou o mesmo UID de alvo em 100% dos 52 eventos correlacionados.
- `0x0C07`: sincronismo de HP de world boss; layout estrutural conhecido.
- `0x0C08`: contribuição pessoal de world boss; layout estrutural conhecido.
- `0x0C05` e `0x0C0A`: listas de resultado/top players, com registros de 33
  bytes. Os campos internos continuam `r0..rN` até captura marcada confirmar a
  semântica.
- `0x0C0B` e `0x0D6B`: estado/final de guild raid, somente estrutura.
- `0x0C11`, `0x0C14` e `0x0C16`: estado/resultado de party dungeon, somente
  estrutura.

## Limites deliberados

- `0x031D FG2C_notify_boss_result_Message` está confirmado no catálogo como a
  mensagem de resultado do boss, mas não possui layout fechado no artefato
  atual. Recompensa e recebedor não são persistidos até existir captura marcada
  suficiente para um golden frame.
- Relação aliado/inimigo usa apenas `realm` confirmado. Guilda, grupo e raid
  só aparecem quando o próprio evento decodificado fornece identificador.
- DPS do boss é a perda de HP entre leituras. Top damage é somente dano
  observado nos resultados de habilidade presentes no stream; não representa
  participantes invisíveis ou pacotes perdidos.
- Retratos usam `assets/mob-icons/<npc_index>.*`. Nenhum catálogo validado de
  retratos acompanha a fonte atual, portanto a interface usa um marcador neutro
  até os assets corretos serem extraídos e associados.

## Validação ainda necessária com jogo real

1. Duas instâncias por pelo menos 30 minutos, com PvE e PvP simultâneos.
2. Boss observado sem ataque local e depois com dano de vários participantes.
3. Evento `0x031D` marcado com recompensa visível e recebedor conhecido.
4. Party e raid com mudanças controladas de membros para fechar IDs e campos.
5. Teste de 12 horas para uso de RAM, perda de pacotes e latência p95.
