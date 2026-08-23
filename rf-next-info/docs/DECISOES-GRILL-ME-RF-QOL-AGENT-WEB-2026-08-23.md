# Decisões do Grill Me — RF QOL Agent e plataforma web

Data de consolidação: 23 ago 2026

Estado: decisões de produto e arquitetura aprovadas pelo owner. Este documento
não autoriza implementação, servidor, instalador, publicação ou mudança em
produção.

## 1. Objetivo do produto

- O RF QOL permanece um projeto pessoal; retorno financeiro é bônus, não
  objetivo ou critério principal de continuidade.
- Sucesso será avaliado por utilidade, estabilidade, qualidade dos dados e uso
  real das funções, não por receita.
- Agent e programas de monitoramento são executáveis separados.
- O usuário normal usa o Agent para captura/decode/envio e o site para consulta.

## 2. Experiência do Agent

- Ícone na bandeja com janela pequena sob demanda.
- Opção de iniciar com o Windows, desativada por padrão.
- Captura iniciada manualmente por padrão, com opção de início automático.
- Quando todos os clientes fecharem, o Agent continua aberto e encerra somente
  captura e sessões aplicáveis.
- Permite pausar toda a captura ou um cliente individual.
- O instalador configura uma única vez o serviço autorizado necessário ao
  Pktmon, evitando pedidos de privilégio em toda abertura.

A janela pequena mostra:

- captura ligada/desligada;
- clientes e personagens reconhecidos;
- conexão com servidor e último envio;
- fila offline e uso de RAM;
- versão e atualização;
- botão para abrir o site;
- pareamentos da API local;
- diagnóstico para suporte.

Notificações do Windows:

- início/fim da captura;
- cliente reconhecido/desconectado;
- indisponibilidade/recuperação do servidor;
- fila offline ou RAM próximas do limite;
- atualização disponível/necessária.

Erro técnico permanece na janela e no diagnóstico, sem notificação operacional
obrigatória. Alertas de Boss, PvP e drops não fazem parte desta regra geral.

## 3. Conta, Profile e acesso

- Vinculação por código curto exibido no Agent e confirmado no site.
- Um computador pertence a apenas um Profile.
- Proprietário e administradores do Profile visualizam computadores, clientes
  e sessões.
- Beta somente por convite.
- Limitações comerciais, planos e módulos são aplicados no site, não no Agent.
- Sem validação, o Agent continua por até sete dias; depois pausa novos
  registros até revalidar.
- Pelo site, o proprietário pode desvincular uma instalação perdida. Quando ela
  voltar a conectar, deve apagar dados locais e revogar todos os pareamentos da
  API local.

## 4. Clientes e sessões

- Todos os clientes encontrados são monitorados por padrão, com desativação
  individual.
- Antes de reconhecer o personagem, usar `Cliente 1`, `Cliente 2` etc.
- Evento ambíguo permanece não atribuído e não entra nas métricas individuais.
- A sessão do cliente começa quando sua conexão é reconhecida.
- Fechamento do jogo e logout encerram automaticamente a sessão.
- Troca de personagem e reinício do Agent não encerram uma sessão por simples
  presunção; exigem regra de continuidade baseada em evidência.

## 5. Offline, armazenamento e memória

- A outbox offline preserva dados por até sete dias e respeita o limite de
  armazenamento escolhido pelo usuário, valendo o primeiro limite atingido.
- Ao atingir o limite, preservar sessões, EXP e combate e descartar primeiro
  domínios menos prioritários. A ordem exata de descarte ainda precisa ser
  definida.
- RAM padrão: 1 GiB, configurável.
- O instalador pergunta o limite inicial de RAM.

Sem o site, continuam funcionando:

- captura e outbox;
- API local de Boss/PvP;
- overlays locais;
- sons e alertas locais;
- exportações locais.

O resumo local de clientes/sessões não foi selecionado como requisito offline.

## 6. Prioridades do primeiro corte

Prioridades locais do Agent:

1. janela de status e controles de captura;
2. API local;
3. overlays;
4. exportações CSV;
5. diagnóstico;
6. atualização automática com confirmação para reiniciar.

Sons e alertas continuam desejados offline, mas não pertencem ao primeiro grupo
prioritário.

Prioridades de envio/processamento no site:

1. presença, clientes e sessões;
2. EXP, level, créditos e contribuição;
3. drops próprios;
4. drops anunciados de outros jogadores;
5. Boss;
6. Ranking Top 100 de EXP;
7. mercado e undercut.

Status, mapa/proximidade, PvP e Banco PvE permanecem planejados, fora do primeiro
grupo prioritário.

## 7. API local

- Somente programas oficiais Karvalho podem consumir a API.
- Cada programa possui autorização própria, visível e revogável.
- Pareamento expira após sete dias sem validação.
- Sem cota comercial de consumidores simultâneos; valem limites técnicos de
  RAM, concorrência e taxa.
- Entrega somente eventos sanitizados. Cada programa calcula seu estado.
- Meta de latência será definida após medição real.
- Documentação interna, restrita ao desenvolvimento Karvalho.
- Permanentemente somente leitura.

## 8. Monitor de Boss

O Boss começa por qualquer uma destas evidências:

- mensagem de posição;
- aparição de NPC conhecido no catálogo;
- aparição de NPC com HP oculto.

Regras:

- expira após 30 segundos sem nova evidência;
- após troca de rota, mapa ou cliente, aguarda até 30 segundos e continua apenas
  se a identidade for novamente confirmada;
- jogador sem guilda confirmada entra em `Não classificado` e é movido quando
  houver confirmação.

Métricas:

- dano acumulado total;
- DPS dos últimos 10 segundos;
- percentual do dano total;
- estimativa de tempo restante;
- HP atual e máximo;
- dano total por guilda;
- ranking individual pelo dano total acumulado.

Superfícies:

- programa oficial separado: colunas por guilda, com seus jogadores dentro;
- site: apresentação configurável pelo usuário.

O Agent mantém apenas IDs e regras mínimas de reconhecimento. O programa de
monitoramento mantém nomes, imagens e catálogo de apresentação.

## 9. Monitor PvP

- Pertence ao programa oficial de monitoramento, separado do Agent.
- PvP é confirmado por dano entre jogadores reconhecidos ou aviso específico de
  PvP do jogo.
- Categorias: própria guilda, aliado, inimigo confirmado, não classificado, alvo
  atual e atacante recente.
- Jogador visível sem relação/evidência fica como `Não classificado`.
- Correlação insegura causada por ExitLag/rotação também permanece como
  `Não classificado`.

Expiração padrão, configurável pelo usuário:

- alvo atual: 10 segundos;
- atacante recente: 10 minutos;
- jogadores próximos: 5 segundos.

O Monitor PvP não terá alertas nesta etapa.

## 10. Catálogo de personagens e UIDs

- O banco central mantém nome, UID de personagem e level confirmados.
- O Agent sincroniza ao abrir e, por padrão, a cada 30 minutos.
- O intervalo é configurável.
- UID de personagem ausente no catálogo sincronizado é enviado ao site para
  confirmação.
- `character_uid` é permitido nesse contrato.
- UID de sessão/login/autenticação continua proibido, assim como tokens,
  tickets, credenciais e payload `0x0101`.
- O catálogo local deve ser protegido e conter apenas os campos necessários.

## 11. Privacidade, áreas públicas e compartilhamento

- Painel combina dados pessoais privados e áreas comunitárias públicas.
- Nomes de personagens e guildas podem aparecer publicamente em Boss e ranking.
- Boss e ranking são áreas públicas.
- Dados detalhados do personagem, drops pessoais, EXP, sessões e subsessões são
  privados, com opção de compartilhamento pelo proprietário.
- Mercado público: preços observados e capturas de mercado.
- Mercado privado e compartilhável: compras, vendas e listagens do usuário.
- Banco PvP é público.
- Alterações pendentes do Banco PvP ficam visíveis somente aos administradores
  do site até aprovação.

Fluxos comunitários:

- processamento automático e uso no site em tempo próximo do real: drops,
  Ranking de EXP e mercado;
- staging para análise antes de alterar conteúdo público: mapas, monstros, Boss
  e PvP.

Detalhe ainda aberto: definir exatamente qual projeção agregada/comunitária de
drops será pública sem tornar público o histórico pessoal de drops.

## 12. Retenção

| Categoria | Retenção |
|---|---:|
| Eventos decodificados | Até processamento confirmado |
| Sessões e subsessões | 3 meses |
| EXP e ranking | 1 mês |
| Drops | 1 mês |
| Boss | 1 mês |
| PvP | 1 semana |
| Mercado | 3 meses |
| Auditoria e segurança | 3 meses |

- Usuário pode exportar por categoria em CSV e JSON.
- Exclusão segue os prazos e regras de retenção.
- Envio Agent → site é automático; não depende de exportação manual.

## 13. Site e celular

- Site pode sincronizar somente configurações seguras, como limites, intervalos
  e categorias de captura.
- Isso não autoriza controle do jogo e não altera a API local somente leitura.

Áreas com experiência móvel obrigatória:

- resumo dos clientes;
- sessões e EXP;
- Boss ao vivo;
- drops;
- mercado;
- configurações do Profile e Agent.

## 14. Atualização e compatibilidade

- Agent baixa a atualização automaticamente.
- Usuário confirma antes de reiniciar e aplicar.
- Servidor aceita a versão atual e a imediatamente anterior.
- Matriz de compatibilidade registra versão, schema, tipo de evento e campos que
  ainda podem ser processados.
- Dados incompatíveis da versão anterior são rejeitados ou isolados; nunca são
  promovidos para comprometer o banco.
- Exportação feita pela versão anterior gera aviso solicitando atualização.

Mitigações obrigatórias para Windows/antivírus:

- executável e instalador assinados;
- download HTTPS;
- verificação de assinatura e SHA-256;
- sem scripts remotos, injeção, hook, ofuscação agressiva ou troca silenciosa do
  executável;
- validação com diferentes antivírus antes da distribuição.

## 15. Diagnóstico e telemetria

Telemetria contínua para todos os usuários, limitada a:

- versões do Agent, decoder e Windows;
- estado da captura e códigos de erro;
- RAM, CPU, disco e filas;
- contadores por tipo sem conteúdo bruto;
- clientes por referências opacas;
- amostras de eventos sanitizados;
- conexão e respostas do servidor.

Exige aviso claro de privacidade, retenção definida e bloqueio técnico de campos
proibidos. A retenção da telemetria deve ser alinhada à auditoria/segurança ou
aprovada separadamente.

## 16. Qualidade, beta e rollback

Ordem de severidade:

1. dado incorreto processado/publicado;
2. mistura entre clientes;
3. RAM acima do limite;
4. atraso nos monitores;
5. perda de eventos;
6. indisponibilidade temporária.

Critérios aprovados:

- zero mistura entre clientes;
- zero dado incompatível promovido;
- RAM dentro do limite configurado, com margem máxima de 10%;
- nenhuma tendência contínua de crescimento de memória;
- zero perda de evento essencial em operação normal;
- recuperação após queda de internet e reinício;
- CPU e latência medidas antes de receberem metas.

Não haverá duração mínima de ensaio nem quantidade fixa de usuários/clientes
como condição abstrata de aprovação.

Qualquer item abaixo interrompe a distribuição até correção ou rollback:

- mistura entre clientes;
- dado incorreto publicado;
- RAM excedida repetidamente;
- perda de eventos essenciais;
- atualização classificada/bloqueada como maliciosa em quantidade relevante;
- falha de captura/envio para parte relevante dos usuários;
- vulnerabilidade ou vazamento.

Ambientes obrigatórios nos primeiros testes:

- cliente PC único;
- múltiplos clientes PC;
- ExitLag;
- diferentes antivírus;
- internet instável/offline;
- múltiplos programas oficiais consumindo a API local.

Emuladores não fazem parte da primeira cobertura obrigatória.

## 17. Detalhes ainda abertos

1. Ordem de descarte dos domínios quando a outbox atingir o limite.
2. Regra de continuidade após troca de personagem e reinício do Agent.
3. Campos exatos e proteção do catálogo local de personagens.
4. Projeção pública/comunitária de drops versus histórico pessoal privado.
5. Retenção e aviso detalhado da telemetria contínua.
6. Allowlist exata das configurações que o site pode sincronizar ao Agent.
7. Metas de CPU e latência, somente após medição real.
8. Matriz formal de compatibilidade entre versão atual e anterior.
9. Critério técnico para `HP oculto` como evidência de Boss.

## 18. Próximo gate recomendado

Transformar as decisões em contratos versionados de produto, dados e segurança,
começando pelos detalhes abertos 1–6. Somente depois revisar o escopo executável
do primeiro beta. Implementação, servidor, instalador e publicação continuam
gates independentes.

Custo real: `unknown`. Rollback preservado:
`rf-qol-desktop-2.0.0-beta.6` / commit `795333d`.
