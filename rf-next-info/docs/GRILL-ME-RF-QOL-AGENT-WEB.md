# Grill me — RF QOL Agent e plataforma web

Data: 22 ago 2026
Estado: questionário de descoberta; nenhuma resposta autoriza implementação,
servidor, publicação ou mudança comercial.

## Como responder

O questionário deve ser conduzido em rodadas curtas. Em perguntas com opções,
responda pelo número e letra, por exemplo: `1B, 2A, 3C`. Comentários livres são
bem-vindos. Quando uma resposta depender de teste real, use `MEDIR` em vez de
escolher um número arbitrário.

Escala de interesse dos módulos:

- `0` — não quero;
- `1` — talvez no futuro;
- `2` — útil, mas não prioritário;
- `3` — importante;
- `4` — muito importante;
- `5` — essencial para lançar.

## Decisões já confirmadas

Estas perguntas não serão refeitas, salvo se o owner quiser revisar a decisão:

- Agent e Desktop são programas e executáveis separados;
- o usuário normal utilizará somente o Agent;
- haverá uma única hospedagem central administrada pelo owner, não um servidor
  por usuário;
- o Agent captura passivamente, reagrupa, decodifica, sanitiza, mantém outbox e
  envia; o servidor processa e o site apresenta;
- o servidor não recebe pacote bruto e não executa outro decoder;
- o Desktop atual fica como referência interna e rollback;
- a quantidade de clientes não terá uma cota comercial fixa no Agent;
- a API local de Boss/PvP é somente leitura, autenticada e limitada a
  `127.0.0.1`;
- não haverá injeção, hook, OCR, automação ou controle do jogo;
- tokens, tickets, credenciais e payload `0x0101` não podem ser persistidos ou
  enviados.

## Rodada 1 — Identidade do produto e experiência básica

1. Como o Agent deve aparecer normalmente?
   - A. Ícone na bandeja e janela pequena quando aberta.
   - B. Janela sempre visível.
   - C. Serviço invisível, com configuração somente pelo site.

2. Ao entrar no Windows, o Agent deve:
   - A. Iniciar automaticamente, com opção para desativar.
   - B. Iniciar somente quando o usuário abrir.
   - C. Ser obrigatório no início do Windows.

3. A captura deve começar:
   - A. Automaticamente ao reconhecer o primeiro cliente do jogo.
   - B. Apenas por botão no Agent.
   - C. Automática por padrão, com modo manual opcional.

4. Quando todos os clientes do jogo fecharem, o Agent deve:
   - A. Continuar aberto e encerrar somente a sessão/captura.
   - B. Encerrar completamente.
   - C. Perguntar após um tempo configurável.

5. Qual informação mínima deve existir na janela do Agent? Escolha todas:
   - A. Captura ligada/desligada.
   - B. Quantidade e nomes dos personagens reconhecidos.
   - C. Estado do servidor e horário do último envio.
   - D. Tamanho da fila offline e uso de RAM.
   - E. Versão e atualização disponível.
   - F. Botão para abrir o site.
   - G. Botão para parear a API local.
   - H. Diagnóstico/exportação de suporte.

6. O usuário deve poder pausar somente um cliente ou apenas a captura inteira?

7. Se o Agent precisar de privilégio de administrador para o Pktmon, prefere:
   - A. Solicitar ao abrir.
   - B. Instalar um serviço autorizado uma vez.
   - C. Escolher depois de um ensaio das duas opções.

8. O Agent deve mostrar notificações do Windows para quais situações?

## Rodada 2 — Conta, acesso e licença

9. Como o Agent deve ser vinculado à conta do site?
   - A. Abrir o navegador e confirmar o computador.
   - B. Código curto mostrado pelo Agent e digitado no site.
   - C. Login e senha dentro do Agent.

10. Um computador pode ficar vinculado a quantos Profiles?

11. Mais de uma pessoa do mesmo Profile poderá ver os mesmos computadores e
    sessões? Se sim, quais papéis: owner, administrador, membro, somente leitura?

12. Durante o beta, o acesso será:
    - A. Livre para qualquer conta.
    - B. Por convite.
    - C. Por licença, porém sem cobrança.

13. Depois do beta, quais partes serão gratuitas e quais dependerão de módulo ou
    plano? Ainda existe interesse em licenciar módulos individualmente?

14. Se a licença/conta não puder ser revalidada, quais funções locais continuam
    e por quanto tempo?

15. O usuário pode desvincular e apagar remotamente uma instalação perdida?

## Rodada 3 — Clientes, sessões e funcionamento offline

16. O Agent deve descobrir automaticamente todos os clientes PC e emuladores,
    ou o usuário escolhe quais serão monitorados?

17. Como nomear clientes antes de reconhecer o personagem: `Cliente 1`, nome do
    processo/emulador ou nome definido pelo usuário?

18. Se a identidade de um evento estiver ambígua entre dois clientes, prefere:
    - A. Manter como não atribuído.
    - B. Tentar atribuir pela hipótese mais provável.
    - C. Não guardar o evento.

19. A sessão deve começar no primeiro reconhecimento confirmado do personagem,
    na abertura do jogo ou no primeiro evento de EXP/combate?

20. O que encerra automaticamente uma sessão: fechamento do cliente, logout,
    troca de personagem, inatividade, reinício do Agent ou ação no site?

21. Quanto tempo sem internet o Agent deve preservar a outbox: por prazo, por
    tamanho ou pelo primeiro limite atingido?

22. Quando o limite de disco for atingido, prefere:
    - A. Remover os eventos mais antigos ainda não enviados.
    - B. Parar de registrar os novos.
    - C. Preservar métricas essenciais e descartar domínios menos importantes.

23. Qual deve ser o limite padrão de RAM do Agent? Use `MEDIR` se quiser decidir
    após ensaio real prolongado.

24. Quais funções precisam continuar funcionando se o site ficar indisponível?

## Rodada 4 — Interesse e ordem das funcionalidades

Avalie de `0` a `5` e marque seus cinco itens mais importantes:

25. Resumo geral de todos os clientes.
26. Sessões e subsessões.
27. Status `Teleportando > PvP > Farm > Ocioso`.
28. Mapa, região, coordenadas e proximidade.
29. EXP, recursos e contribuição por sessão/hora.
30. Ranking Top 100 de EXP e histórico.
31. Drops próprios e alertas por categoria/raridade.
32. Drops anunciados de outros jogadores.
33. Monitor de Boss, vida, DPS total e guildas.
34. Monitor PvP, alvo atual e proximidade.
35. Banco PvE e localização de monstros.
36. Mercado/leilão, histórico e undercut.
37. Exportações CSV.
38. Alarmes, sons e notificações remotas.
39. Overlays locais.
40. API local para programas externos.
41. API web para integrações autorizadas.

Pergunta de corte: quais três itens você aceitaria remover do primeiro beta para
lançar mais cedo com estabilidade?

## Rodada 5 — API local e programas externos

42. Quem poderá consumir a API local?
    - A. Somente programas oficiais Karvalho.
    - B. Programas de terceiros aprovados.
    - C. Qualquer programa que o usuário parear.

43. Um pareamento deve durar até revogação, expirar periodicamente ou valer
    somente enquanto o Agent estiver aberto?

44. O usuário precisa ver e revogar separadamente cada programa pareado?

45. Quantos consumidores simultâneos devem ser aceitos?

46. A API deve entregar apenas eventos para o programa calcular tudo, ou também
    snapshots prontos de alvo PvP, chefe atual, HP e DPS?

47. Se Boss/PvP precisar de latência abaixo de um segundo, qual atraso máximo é
    aceitável: 100 ms, 250 ms, 500 ms, 1 s ou `MEDIR`?

48. A documentação da API será pública ou somente para parceiros aprovados?

49. A API continuará estritamente somente leitura no futuro? Que tipo de comando
    você considera proibido sem exceção?

## Rodada 6 — Monitor de Boss

50. O início do Boss exige catálogo conhecido, mensagem de posição, aparição do
    NPC ou qualquer combinação dessas evidências?

51. Quando o chefe sai de proximidade sem mensagem final, após quanto tempo seu
    estado deve desaparecer?

52. DPS deve apresentar dano acumulado total, DPS médio desde o início, janela
    recente ou os três?

53. O ranking principal deve ser por jogador, guilda ou permitir alternância?

54. Jogador sem guilda e guilda não confirmada devem ficar separados?

55. O monitor local deve funcionar integralmente sem internet? Quais dados do
    catálogo precisam ficar dentro do Agent para isso?

56. O que deve acontecer ao trocar de rota, mapa ou cliente durante um Boss?

## Rodada 7 — Monitor PvP

57. O que confirma PvP: dano entre jogadores, aviso específico do jogo,
    atacante confirmado, alvo selecionado ou uma combinação?

58. Quais categorias devem existir: aliado, inimigo confirmado, não classificado
    e membro da própria guilda? Há outras?

59. Um jogador visível, mas sem relação de guilda, aparece em qual lista?

60. Após desaparecer ou parar o combate, em quantos segundos alvo e proximidade
    devem ser removidos?

61. É aceitável mostrar `não classificado` quando ExitLag ou rotação de fluxo
    impedir correlação segura, em vez de arriscar uma atribuição errada?

62. Nomes de jogadores e guildas podem ser enviados ao site, devem ser
    pseudonimizados ou ficam somente no computador?

63. Quais alertas PvP justificam som, overlay, notificação do Windows ou alerta
    remoto?

## Rodada 8 — Site, dados e compartilhamento

64. O painel é privado por usuário/Profile ou haverá páginas compartilháveis?

65. Por quanto tempo guardar: eventos decodificados, sessões, rankings, drops,
    Boss, PvP e auditoria?

66. O usuário pode apagar/exportar todos os próprios dados? Em qual formato?

67. Quais dados podem alimentar bancos comunitários: mapa, monstros, HP de Boss,
    drops, ranking e mercado?

68. Dados comunitários devem ser anônimos, pseudônimos ou vinculados ao nome do
    personagem?

69. O site pode enviar configurações ao Agent no futuro ou continuará sem canal
    de comando remoto?

70. Quais visualizações precisam funcionar bem no celular?

## Rodada 9 — Atualização, suporte e critérios de lançamento

71. Atualizações do Agent serão automáticas, opcionais ou obrigatórias quando o
    protocolo mudar?

72. Quantas versões antigas devem continuar aceitas pelo servidor?

73. Que diagnóstico o usuário pode enviar ao suporte sem expor dados pessoais?

74. Qual falha é mais grave: perder alguns eventos, misturar clientes, consumir
    RAM demais, atrasar o monitor ou ficar indisponível?

75. Quais metas definem um beta aceitável: duração do ensaio, quantidade de
    clientes, RAM máxima, CPU média, latência e perda tolerada?

76. Qual é o sinal de que o beta deve parar e voltar ao Desktop?

77. Quem serão os primeiros usuários de teste e que variedade de PC, emulador,
    ExitLag e quantidade de clientes precisamos cobrir?

78. Quais métricas de interesse definirão se o produto vale continuar: usuários
    ativos, horas capturadas, sessões consultadas, uso de Boss/PvP, retenção ou
    outra?

## Resultado esperado

Depois das respostas, consolidar:

1. visão do produto e público-alvo;
2. funcionalidades `agora`, `depois` e `não fazer`;
3. comportamento detalhado do Agent e de cada monitor;
4. contrato de privacidade e retenção;
5. metas mensuráveis do beta;
6. gates de implementação, servidor, instalador e publicação;
7. lista explícita de hipóteses que ainda dependem de captura ou ensaio real.
