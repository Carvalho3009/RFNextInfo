# Changelog

## 2.0e — 2026-07-31

- subsessões selecionadas podem ser renomeadas ou excluídas localmente;
- exclusão preserva os eventos da captura e dados já enviados ao site;
- seleção de mobs usa caixas de marcação em três colunas e remove prefixos
  técnicos dos nomes exibidos.

## 2.0d — 2026-07-31

- localização, spot e mobs podem ser exibidos em Português ou English;
- a captura mantém um heartbeat supervisionado pela interface;
- se o aplicativo encerrar ou parar de responder por 45 segundos, o vigia
  local encerra o PktMon e remove os filtros para impedir arquivos excessivos.

## 2.0c — 2026-07-30

- EXP, créditos e contribuição do farm passam a usar a recompensa-base do
  monstro; o bônus de finalização não infla mais os totais nem as taxas.
- Finalizações são contabilizadas separadamente e pacotes sem recompensa de
  EXP não são considerados abates.
- O loot é separado em comum, incomum, raro e épico usando os 8.192 itens da
  base canônica 1.28.5.
- A visão geral e as subsessões exibem os totais corrigidos, incluindo
  contribuição total e por hora.
- O envio de personagem inclui os equipamentos e a pasta das capturas pode
  ser escolhida nas configurações.

## 2.0b — 2026-07-30

- O catálogo de farm passa a usar seleção encadeada de mapa, spot e mobs.
- A subsessão aceita mob extra, nível, observação e duração própria; duração
  `0` permanece ativa até o encerramento manual.

## 2.0a — 2026-07-30

- O Rover equipado na entrada é lido diretamente do `0x0305` do próprio
  personagem; não é mais necessário trocar o Rover para exibi-lo.

## 1.0.24 — 2026-07-30

- O leitor incremental reutiliza a correlação canônica entre aparência e
  inventário para exportar os equipamentos ativos.
- Personagem, Codex e Memory Chips enviam cargas separadas; Codex envia apenas
  coleções e Memory Chips envia apenas chips.
- O site aceita o resumo de captura antigo como fallback para classe, nível,
  Biosuit, Rover e equipamentos, e recarrega os dados ao voltar para a janela.

## 1.0.23 — 2026-07-30

- Personagem, Mercado, Codex e Memory Chips passam a enviar ao site os dados
  já lidos pela captura contínua; os botões e atalhos não iniciam novas
  capturas.
- O encerramento mostra o progresso real da leitura por segmento.
- Subsessões encerradas podem ser selecionadas e enviadas individualmente,
  com identificador cumulativo persistente e proteção contra duplicidade.

## 1.0.22 — 2026-07-30

- O aplicativo passa a se chamar RF NEXT QOL e exibe o novo logo junto ao
  símbolo do urso com K.
- O ícone da classe usa a cor da raridade confirmada pelo `Grade` do Biosuit.
- Trocas de Biosuit confirmadas durante a captura atualizam classe, nome,
  raridade e ícone sem aguardar o encerramento da sessão.
- O Rover equipado é identificado por eventos confirmados, exibido com nome e
  ícone à esquerda da classe; solicitações e respostas com erro são ignoradas.

## 1.0.21 — 2026-07-30

- O mesmo token de Profile autentica os envios de Farm, Codex, Memory Chips
  e Mercado.
- Capturas rápidas decodificadas são enviadas em segundo plano sem encerrar a
  captura contínua; falhas ficam pendentes no banco local para nova tentativa.
- Codex e Memory Chips são mesclados ao progresso existente, sem apagar
  coleções que não estavam na captura rápida.

## 1.0.20 — 2026-07-30

- Iniciar com “Descartar sessão anterior” não consulta o Pktmon nem apresenta
  erro quando existe apenas um identificador antigo, sem arquivos reais.
- Cada subsessão pode receber uma duração própria em minutos e é encerrada
  automaticamente no prazo informado.
- O catálogo 1.28.5 de localização, mob e nível passa a acompanhar o programa;
  escolher a localização filtra os mobs e preenche o intervalo de níveis.
- O histórico e o JSON das subsessões incluem EXP total, EXP total em
  percentual, EXP/h e EXP/h em percentual.

## 1.0.19 — 2026-07-30

- A leitura ao vivo usa segmentos fechados por intervalo e continua gravando
  em paralelo, sem o limite permanente de 512 MB da prévia.
- Os clientes exibem separadamente o nome manual e o nome capturado; o nome
  manual não identifica nem renomeia dados exportados.
- As durações mostram segundos ou minutos e todas as páginas possuem rolagem
  vertical e horizontal quando o conteúdo ultrapassa a janela.
- O aplicativo e a bandeja usam o símbolo do urso com K.

## 1.0.18 — 2026-07-29

- Segmentos residuais vazios não anulam mais os eventos decodificados nem
  deixam a sessão presa em reanálise.
- A retomada automática é interrompida quando existe uma falha real pendente.
- Em uma sessão de cliente único, o `0x0106` canônico vincula o personagem ao
  Cliente A mesmo depois de uma troca de porta não observada pelo Windows.
- Uma identidade heurística nunca substitui a identidade canônica e é
  recusada quando o mesmo pacote contém mais de uma aparição de personagem.
- O preview bruto é preservado quando nenhuma rota de cliente corresponde aos
  pacotes, permitindo a decodificação após relog ou troca de porta.

## 1.0.17 — 2026-07-29

- Mantém o histórico de portas de cada cliente durante reconexões e na
  análise final.
- Identifica o personagem somente pela sequência completa de entrada marcada,
  dentro da janela escolhida e numa porta confirmada do Cliente A/B.
- Não usa aparições comuns de outros jogadores como identidade do usuário.

## 1.0.16 — 2026-07-29

- Alternar Cliente A/B não abre mais a edição do nome; cada cliente possui um botão Renomear.
- Novas conexões permanecem vinculadas ao processo correto durante a captura ao vivo.
- EXP, Loot e personagem são atualizados nas leituras periódicas, sem aguardar Parar.
- EXP faltante e EXP/h (%) usam a exigência correta do próximo nível.
- Diamantes são exibidos somente quando UID ou nome confirmam o próprio personagem.
- Cada captura rápida possui duração própria entre 10 e 300 segundos.
- Os quatro cartões de captura rápida usam a mesma altura e alinhamento.

## 1.0.15 — 2026-07-29

- Separa automaticamente Cliente A e Cliente B pelas portas de cada processo.
- Mantém a separação nas leituras ao vivo e na análise final dos segmentos.
- Usa somente a entrada do próprio personagem para confirmar UID e nome.
- Remove a logo Karvalho do cartão reservado ao símbolo da classe.

## 1.0.14 — 2026-07-29

- Capturas rápidas agora aceitam duração configurável de 10 a 300 segundos.
- Atalhos receberam contraste dourado nos cartões e nas configurações.
- Removidas bordas internas que atravessavam textos e dados dos painéis.
- Cabeçalho e marca lateral foram redimensionados para aproveitar melhor o espaço.

## 1.0.13 — 2026-07-29

- Adicionada opção confirmada para limpar a sessão anterior antes de iniciar.
- A limpeza inclui arquivos brutos ainda não decodificados e os envia à Lixeira.
- O histórico, as janelas de captura e as subsessões da sessão descartada também são removidos.

## 1.0.12 — 2026-07-29

- alinha a estrutura das quatro telas ao mockup aprovado;
- corrige o cronômetro para não avançar com a captura parada;
- torna explícitos os estados disponível, ativo, pausado e encerrado;
- recupera e analisa uma captura pendente antes de iniciar a próxima;
- habilita pausa e continuação da mesma sessão.

## 1.0.11 — 2026-07-29

- recompõe as telas conforme o mockup aprovado com fontes e marca Karvalho;
- corrige a validação do token do Profile pela API pública autenticada;
- corrige capturas rápidas e subsessões durante a captura contínua;
- detecta automaticamente o executável `ProjectRF` conectado;
- amplia o autoteste do instalador para construir toda a interface.

## 1.0.10 — 2026-07-29

- valida a licença salva em segundo plano ao abrir e atualiza o estado da tela;
- atualiza informações durante a captura usando o preview nativo do PktMon;
- preserva a captura ETL completa como fonte da exportação.

## 1.0.9 — 2026-07-28

- portas locais e remotas do `ProjectRF` passam pela captura e pela análise;
- a porta RF `12010` entra no conjunto conhecido e recupera eventos antes
  presentes no ETL, mas ignorados pelo decoder;
- a parada é idempotente e impede análises concorrentes da mesma sessão;
- ETL sem pacotes permanece pendente e preservado para nova análise;
- mudanças no decoder, catálogo ou portas reprocessam capturas antigas;
- a tela exibe os contadores de pacotes do PktMon quando disponíveis;
- o parser PCAPNG valida blocos truncados e informa diagnóstico seguro;
- fluxos TCP com gap tentam ressincronização somente após três frames válidos.

## 1.0.8 — 2026-07-28

- a exportação pergunta a EXP atual quando há um UID confirmado e eventos
  restantes sem identificação;
- o fluxo de EXP mais próximo é associado ao personagem confirmado;
- o CSV de captura inclui licença, instalação e marcações de Codex para
  importação segura no site;
- o site distingue CSV de captura de CSV de Mercado pelo cabeçalho.

## 1.0.7 — 2026-07-28

- removida a seleção manual de processo por personagem introduzida na 1.0.6;
- todas as conexões dos clientes `ProjectRF` são capturadas automaticamente;
- PID, porta e ordem dos processos não são usados como identidade de personagem;
- a separação usa somente UID confirmado ou a EXP (%) informada na exportação.

## 1.0.6 — 2026-07-28

- cada nome de personagem é vinculado explicitamente a um processo `ProjectRF`;
- portas locais de cada processo identificam os eventos sem depender da
  presença eventual do UID no protocolo;
- filtros das portas conhecidas do jogo já ficam ativos antes do login e
  continuam cobrindo reconexões;
- exportações incompletas geram alerta e marca de revisão, sem bloquear os
  arquivos JSON/CSV;
- sem UID, a EXP atual (%) informada associa cada personagem à conexão mais
  próxima; eventos restantes seguem em arquivo separado para revisão;
- logs usam o horário local do computador com o deslocamento UTC explícito;
- empacotamento alterado para diretório interno instalado, eliminando a
  extração `_MEI` temporária que causava a falha de `python313.dll`;
- autoteste do instalador continua obrigatório, agora usando as DLLs instaladas.

## 1.0.5 — 2026-07-28

- licença persistida em arquivo DPAPI vinculado ao computador, com backup
  criptografado e migração do JSON anterior;
- datas reais de início e vencimento incluídas na lease assinada pelo servidor;
- lista de processos limitada a executáveis cujo nome começa com `ProjectRF`;
- uma captura PktMon anterior é encerrada e seus filtros são removidos antes
  do novo início, com uma repetição controlada para o erro “já foi iniciado”;
- instalador executa o autoteste do programa instalado, salva `install.log` e
  não abre o aplicativo automaticamente ao finalizar.

## 1.0.4 — 2026-07-28

- o usuário escolhe o executável do jogo uma vez e a escolha fica salva;
- as portas TCP locais são descobertas automaticamente por processo, inclusive
  em reconexões, sem capturar toda a rede;
- suporte a até dois processos do jogo conectados ao mesmo tempo;
- capturas sem pacotes terminam normalmente e não geram exportações vazias;
- logs registram códigos sanitizados para falhas de captura e descoberta.

## 1.0.3 — 2026-07-28

- progresso visível durante consulta, download e verificação da atualização;
- o aplicativo salva o estado e encerra antes de o instalador substituir os arquivos;
- o instalador aguarda o fechamento de versões anteriores sem forçar o processo;
- atualização bloqueada durante captura ativa para evitar perda de dados;
- download parcial nunca é tratado como instalador verificado.

## 1.0.2 — 2026-07-28

- licença e logs persistidos na pasta comum do computador, com migração do formato anterior;
- recuperação de captura PktMon que permaneceu ativa após fechamento ou falha;
- arquivos ETL pendentes podem ser parados e analisados sem serem apagados;
- falha ao iniciar não substitui mais a referência da captura anterior;
- exportação permanece disponível mesmo se a licença não for reconhecida;
- botões de enviar, abrir a pasta e salvar uma cópia sanitizada do log no topo da aba Licença.

## 1.0.1 — 2026-07-28

- log técnico local com rotação automática e limite aproximado de 4 MB;
- remoção defensiva de licença, token, e-mail, IP, UUID e usuário do Windows;
- botão independente **Enviar log técnico** na aba Licença;
- upload somente após confirmação, pelo canal de diagnóstico já autenticado.

## 1.0.0 — 2026-07-28

- ativação e preferências preservadas durante atualizações;
- sessões isoladas a cada encerramento de captura;
- suporte a até dois personagens simultâneos por UID confirmado;
- Profile e nomes de personagens persistidos;
- JSON e CSV separados por personagem e sessão;
- nomes `Profile-Personagem-datahora-contador`;
- EXP bruta e percentual no level;
- aba Informações com tempo, level, EXP, créditos confirmados, contribuição,
  mercado, loot e kills estimadas por recompensa;
- diagnóstico separado sem payload, IP, flow, UID, personagem, chave ou licença;
- atualização estável/beta via release GitHub verificada por Ed25519 e SHA-256.
