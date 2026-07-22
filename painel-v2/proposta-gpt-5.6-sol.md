## 1. Conceito

**Console editorial operacional:** a personalidade Karvalho organiza o painel sem competir com os dados.

- Observação primeiro; ações e edição aparecem apenas no contexto necessário.
- Hierarquia por tipografia, alinhamento e bordas — não por uma grade indiscriminada de cards.
- Acid identifica operação ativa/saudável; gold, atenção; coral, falha ou encerramento.
- Ornamentos ficam restritos a cabeçalhos, painéis prioritários e estados críticos.
- Filas, esperas e dados stale permanecem sempre explícitos.
- Densidade adequada ao uso diário, com controles de 32–36 px e texto mínimo de 12 px.
- A proposta usa exclusivamente as rotas existentes; novos comportamentos são de apresentação e navegação.

## 2. Arquitetura de informação

### App shell

- Navegação lateral fixa de **216 px**, fundo coal, borda direita gold a 25%.
- Marca “MCP Control” no topo; abaixo, as oito abas nesta ordem:
  1. Status
  2. Workers
  3. Tools
  4. Orquestrador
  5. Chat/projetos
  6. Grill Me
  7. Uso/custos
  8. Instruções
- Barra operacional superior de **48 px** com:
  - saúde do control-api;
  - estado da conexão e idade do último dado;
  - VRAM usada/total;
  - quantidade aguardando VRAM;
  - quantidade aguardando recurso;
  - projeto ativo, quando aplicável;
  - botão do histórico de notificações.
- Área principal fluida, sem largura máxima artificial, com gutter de 24–32 px.

### Promoções e reagrupamentos

- **Workers** deixa Status e vira área de configuração própria.
- **Uso/custos** sai do Orquestrador e passa a ser uma visão analítica transversal.
- **Grill Me** ganha fluxo próprio, sem ser escondido em Chat ou Orquestrador.
- Status se torna predominantemente observacional.
- Containers e comandos de host saem da telemetria e ficam em **Tools › Runtime e host**, dentro de uma área operacional explicitamente separada.
- Tools passa a reunir catálogo de ferramentas, servidores MCP e infraestrutura acionável.

### VRAM, filas e auditoria

- VRAM aparece resumida na barra global e detalhada em Status.
- A fila `aguardando_vram` fica junto ao gráfico de VRAM, com job, modelo, memória solicitada, tempo e posição.
- A fila global de recursos fica em **Status › Fila de recursos**; suas linhas relevantes reaparecem contextualizadas no Orquestrador e no Chat.
- Auditoria de configuração fica em **Workers**, acessível globalmente e por worker, sem disputar espaço com os campos de edição.
- Cada conversa ou job em `aguardando_recurso` mostra recurso, prioridade e posição no próprio cabeçalho.

### Breadcrumbs e deep-links

A SPA usa estado navegável por hash, sem alterar rotas do control-api:

- `#/workers/{worker}`
- `#/workers/{worker}?project={slug}`
- `#/orchestrator/jobs/{job_id}`
- `#/projects/{slug}/conversations/{id}`
- `#/grill/{session_id}`
- `#/usage?project={slug}&period=30d`

Breadcrumbs aparecem apenas em telas de detalhe, por exemplo:  
**Orquestrador / Jobs / job-1842**.

O login solicita somente o token em campo protegido. Não mostra caminho de arquivo, localização interna ou instruções que exponham onde o token reside.

## 3. Sistema de design

### Tipografia

| Nível | Tamanho | Família e uso |
|---|---:|---|
| Título de página | 40 px / 2.5 rem, linha 36 px | Display, uppercase; uma palavra pode usar coral |
| Métrica principal | 28 px / 1.75 rem, linha 30 px | Display, numerais condensados |
| Título de seção | 24 px / 1.5 rem, linha 26 px | Display, uppercase |
| Título de painel | 16 px / 1 rem, linha 20 px | Display, uppercase, tracking 0.06em |
| Corpo | 14 px / 0.875 rem, linha 20 px | Body |
| Corpo compacto | 13 px / 0.8125 rem, linha 18 px | Body; tabelas e listas densas |
| Navegação, botão e `th` | 13 px / 0.8125 rem, linha 16 px | Display, uppercase, tracking 0.07em |
| Legenda | 12 px / 0.75 rem, linha 16 px | Body, nunca abaixo disso |

A fonte condensada aparece em títulos, rótulos, botões, métricas e cabeçalhos de tabela. Textos longos, mensagens, descrições e valores complexos permanecem em Segoe UI/Inter.

### Espaçamento e geometria

- Escala: **4, 8, 12, 16, 24, 32, 48 px**.
- Altura de controles compactos: 32 px; padrão: 36 px; CTA importante: 40 px.
- Painéis: raio de 2 px.
- Modais e drawers: raio de 4 px.
- Chips: raio de 999 px apenas por necessidade funcional.
- Moldura padrão: 1 px `rgba(212,166,77,.45)`.
- Cantos ornamentais 12×12 px, espessura 2 px, somente em:
  - cabeçalho da página;
  - painel prioritário;
  - modal destrutivo;
  - relatório final do Grill Me.
- Sem sombras difusas. O CTA acid usa o inset duplo da identidade Karvalho.

### Mapeamento dos tokens

| Token | Papel no painel |
|---|---|
| `coal #070909` | Fundo do app, sidebar, fundos de CTA |
| `panel #0e1211` | Superfícies, linhas selecionadas e modais |
| `bone #f4f2eb` | Texto principal, números e títulos |
| `muted #a7a6a0` | Texto secundário, timestamps, estados inativos |
| `gold #d4a64d` | Molduras, divisores, atenção, limite elevado |
| `acid #a8ff16` | CTA, link, seleção ativa, online/saudável |
| `coral #ff6547` | Erro, crítico, encerrado, ação destrutiva |
| `water #63b9f3` | Informação, progresso neutro e focus-visible |
| `violet #8a6ed6` | Categorias secundárias, ferramentas e papéis especiais |
| `display` | Títulos, navegação, botões, métricas e cabeçalhos |
| `body` | Conteúdo, formulários, mensagens e explicações |

### Semântica visual

- Saudável, ativo, live: **acid + ícone + texto**.
- Atenção, saturação, espera longa: **gold + triângulo/rótulo**.
- Erro, indisponível, crítico: **coral + ícone/rótulo**.
- Informativo ou reconectando: **water**.
- Inativo/off: muted, sem reduzir a legibilidade do texto por opacidade.
- Categoria extra: violet; nunca usado sozinho como estado operacional.

Barras:

- abaixo de 75%: acid;
- 75–90%: gold;
- acima de 90%: coral;
- valor indisponível: trilho tracejado muted e rótulo “SEM DADO”.

Sparklines:

- CPU: acid;
- GPU: water;
- VRAM: gold;
- disco: violet;
- erro ou throttling: marcador coral;
- período stale: linha interrompida, não uma continuação falsa.

Badges:

- On/live: fundo acid, texto coal.
- Off: contorno muted, texto muted.
- Warning: fundo gold, texto coal.
- Error/ended: fundo coral, texto coal.
- Waiting: contorno gold com ícone de relógio e posição textual.

### Estados

- **Hover:** superfície gold a 8% ou sublinhado acid; sem deslocamento de layout.
- **Focus-visible:** outline water de 2 px, offset de 2 px.
- **Pressed:** inset acid/gold mais intenso.
- **Disabled:** texto muted legível, superfície sem destaque e motivo visível em tooltip; não usar apenas opacidade.
- **Loading:** skeleton com base gold a 8%; animação de 1,2 s, desativada em reduced-motion.
- **Empty:** painel aberto, título objetivo, explicação de uma linha e ação direta quando existir.
- **Error:** faixa esquerda coral de 3 px, mensagem, tentativa novamente e detalhe recolhível.
- **Stale:** dados preservados, levemente dessaturados, faixa “DADOS DE 38 S ATRÁS” e ação “Reconectar”.
- **Offline:** faixa global coral; ações que dependem de conexão ficam indisponíveis com explicação.

### Componentes-chave

- **OperationalPanel:** cabeçalho, corpo e rodapé opcionais; variantes neutral, metric, warning e danger.
- **DataTable:** cabeçalho fixo, seleção de linha, ordenação clara, colunas numéricas alinhadas à direita e estado vazio interno.
- **Modal:** substitui `alert`, `confirm` e `prompt`; foco preso, título, consequência, conteúdo e rodapé fixo.
- **Drawer:** detalhes, auditoria, filtros avançados e histórico de notificações.
- **Toast + histórico:** toast curto no canto inferior direito e registro no drawer superior, com horário, origem, resultado e link para o objeto relacionado.
- **RoleChip:** allow acid, block coral, inherited muted; removível por botão próprio, não pelo chip inteiro.
- **Toggle:** estado textual “LIGADO/DESLIGADO”, `switch` acessível e confirmação contextual quando houver trabalho ativo.
- **Tooltip:** atraso de 300 ms, acionável por mouse e teclado, nunca contém controles.
- **Skeleton:** replica a geometria final; tabelas usam linhas, não grandes retângulos genéricos.
- **ResourceQueueRow:** recurso, dono, prioridade, posição, espera e link para job/conversa.
- **Progress:** valor, unidade e limiar sempre textuais, não apenas cromáticos.

## 4. Especificação por aba

### Status

**Layout:** grade de 12 colunas. No topo, uma banda gold invertida apenas quando houver incidente geral; em operação normal, quatro métricas compactas: saúde, CPU, GPU/VRAM e armazenamento.

Abaixo:

- área principal de 8 colunas:
  - CPU e memória;
  - GPU e VRAM;
  - disco;
  - sparklines e última atualização;
- área lateral de 4 colunas:
  - saúde do control-api via `GET /api/health`;
  - serviços essenciais;
  - incidentes recentes;
- largura completa:
  - fila `aguardando_vram`;
  - fila global de recursos/locks.

A fila global mostra recurso, dono atual, quem espera, posição e prioridade com ordem visual **interativa › normal › batch**. Se estiver vazia, mostra “Nenhum recurso disputado”.

**Mudança:** deixa de concentrar toggles, containers e comandos host. Torna-se a resposta rápida para “está saudável, saturado ou bloqueado?”.

### Workers

**Layout:** lista mestre de 300 px à esquerda e detalhe flexível à direita. A lista mostra nome, modelo/provider, estado, jobs ativos, pressão de VRAM e versão da configuração.

O detalhe possui quatro seções:

1. **Identidade e estado**
   - nome, provider/model e capacidades;
   - toggle liga/desliga;
   - jobs ativos e fila associada;
   - versão atual e última alteração.

2. **Papéis**
   - grupos “Permitidos” e “Proibidos”;
   - busca de papel e chips allow/block;
   - conflito apresentado inline antes de salvar;
   - estado efetivo diferenciado de estado herdado.

3. **Limites**
   - concorrência máxima;
   - tokens por job;
   - tokens por dia;
   - `keep_alive`;
   - temperatura com campo numérico e controle de faixa nativo.

Tooltip de temperatura:

- `0,00–0,20`: **Juiz — determinístico e conservador**;
- `0,21–0,50`: **Executor — equilibrado**;
- `0,51–0,89`: **Explorador — maior variação**;
- `0,90+`: **Interrogador — divergente e provocativo**.

As faixas são orientação visual, não bloqueio do valor.

4. **Alterações**
   - barra fixa com resumo do diff;
   - descartar e salvar nova versão;
   - erros aparecem junto ao campo e no resumo.

**Matriz por projeto:** subvisão “Overrides”. Linhas são papéis; colunas são workers. Um seletor define o projeto. Cada célula possui três estados: herdado, permitido, proibido. Cabeçalhos e primeira coluna ficam fixos; filtros reduzem workers e papéis sem transformar a matriz em cards.

**Auditoria:** drawer com versão, ator, data/hora, escopo global/projeto e diff antes/depois. É acessível pelo cabeçalho do worker e por cada campo alterado.

**Mudança:** transforma workers de telemetria passiva em configuração operacional versionada, mantendo VRAM, atividade e espera visíveis no mesmo contexto.

### Tools

Três subvisões internas:

- **Servidores MCP**
- **Catálogo e execução**
- **Runtime e host**

Servidores MCP usam tabela com nome, transporte, URL, auth, estado e última verificação. O detalhe permite:

- editar `url` usando o `PATCH` já existente;
- habilitar/desabilitar;
- configurar OAuth/credenciais via `PUT /api/mcp/servers/{id}/auth`;
- mascarar segredos e mostrar somente estado configurado/ausente/expirado.

Catálogo preserva o formulário derivado de JSON Schema, mas separa parâmetros obrigatórios, opcionais e avançados. Resultado, markdown, raciocínio e JSON bruto ficam no mesmo painel, com navegação por teclado.

Runtime e host contém containers e comandos. Ações destrutivas ocupam uma seção própria com moldura coral; parar o container do próprio painel recebe tratamento crítico e não aparece junto a métricas.

**Mudança:** inclui auth e edição de URL, organiza formulários e remove operações perigosas do Status.

### Orquestrador

**Layout:** lista de jobs à esquerda, conteúdo do job ao centro e inspector contextual de 320 px à direita em telas largas.

- Criador de job no topo, com os modos já suportados.
- Lista com status, projeto, modo, prioridade, duração e consumo.
- Detalhe com breadcrumb, linha do tempo das fases, fanout, juiz, resultados e logs.
- Inspector mostra worker/model, parâmetros, recursos adquiridos e links relacionados.
- Job bloqueado exibe banner gold:
  - `AGUARDANDO RECURSO: gpu:0`;
  - posição;
  - dono atual;
  - prioridade;
  - tempo de espera.
- Uso detalhado sai desta aba; permanece apenas um resumo do job com link para Uso/custos.

**Mudança:** deixa de misturar execução, inspeção e analytics. O detalhe deixa de ser uma tela sem contexto graças a breadcrumb e URL própria.

### Chat/projetos

**Layout desktop:** três áreas:

- projetos: 260 px;
- conversas: 320 px;
- conversa ativa: flexível.

O formulário de novo projeto coleta nome, slug e **description**, usando o campo já aceito por `POST /api/projects`.

A conversa possui:

- cabeçalho com projeto, título, estado e ações;
- mensagens em coluna de leitura, sem cards por mensagem;
- raciocínio em disclosure;
- composer fixo no rodapé;
- links para jobs/agentes relacionados.

Mover conversa abre modal com busca e seleção de projeto; não solicita slug textual. Uma conversa em `aguardando_recurso` mostra banner persistente com recurso, posição, prioridade e tempo de espera. O polling nunca remove a mensagem já renderizada durante reconexão.

**Mudança:** substitui `prompt()`, adiciona descrição de projeto, deep-link e estado de espera explícito.

### Grill Me

**Layout:** cabeçalho de sessão, barra de filtros fixa, coluna principal de perguntas e resumo lateral de 280 px.

Filtros:

- categoria;
- severidade;
- estado: aberta, respondida, defendida, risco aceito, descartada;
- busca textual.

Cada card contém número, categoria, severidade, pergunta, evidência/contexto, estado e quatro ações:

1. **Responder** — CTA acid; expande campo de resposta no próprio card.
2. **Defender com agente** — botão water; modal escolhe o agente/worker permitido e mostra execução longa.
3. **Aceitar risco** — botão gold; exige registrar a justificativa exibida no relatório.
4. **Descartar** — ghost muted; solicita motivo curto e encerra a pergunta.

Perguntas resolvidas colapsam para uma linha resumida; a pergunta ativa permanece expandida. Severidade crítica usa faixa coral, ícone e texto, sem depender só da cor.

O resumo lateral mostra totais e pendências. “Finalizar e gerar relatório” permanece visível; se houver questões abertas, a UI explica a regra retornada pelo fluxo e nunca falha silenciosamente. O relatório final recebe moldura ornamental, índice por categoria e links de volta às perguntas.

**Mudança:** cria um fluxo deliberativo rastreável, em vez de representar o Grill como uma saída textual única.

### Uso/custos

**Layout:** filtros horizontais, faixa de totais, gráfico principal e tabela de decomposição.

Filtros:

- período;
- projeto;
- provider/model;
- worker;
- papel;
- modo de orquestração.

Totais:

- tokens de entrada;
- tokens de saída;
- tokens totais;
- custo conhecido/estimado;
- jobs e conversas no período.

Visualizações:

- série temporal alternável entre tokens e custo;
- decomposição por projeto, modelo, worker e papel;
- tabela detalhada com link para job ou conversa;
- comparação com período anterior somente quando os dados necessários existirem.

Custos recebem rótulo explícito:

- **REAL**, quando fornecido;
- **ESTIMADO**, quando calculado com tarifa disponível;
- **SEM TARIFA**, quando não for possível calcular.

“Sem tarifa” nunca aparece como custo zero. Exportação da tabela visível pode ser feita no cliente, sem nova rota.

**Mudança:** promove uso a ferramenta transversal e separa volume, custo e ausência de preço.

### Instruções

**Layout:** lista de escopos/documentos à esquerda e editor com preview à direita.

- Escopo e origem sempre visíveis.
- Editor usa corpo legível, contador e estado de alterações.
- Preview de markdown lado a lado acima de 1100 px.
- Erros de validação aparecem inline.
- Alterações não salvas são preservadas ao tentar trocar de item por meio de modal próprio.
- Estado vazio explica como selecionar ou criar uma instrução apenas quando a operação já for suportada pelas rotas atuais.

**Mudança:** troca a aparência de formulário genérico por uma área de edição estável e evita perda acidental.

## 5. Padrões de interação

### Ações destrutivas

Há três níveis:

- **Rotina reversível:** confirmação inline curta.
- **Destrutiva:** modal com nome do alvo, consequência e CTA coral.
- **Crítica**, como parar o próprio painel: exige digitar o nome exato do container e informa que a UI perderá conexão.

Comandos de host mostram comando, alvo e impacto antes da execução. O botão primário de um modal destrutivo nunca recebe foco inicial; o foco começa em “Cancelar”.

### Operações longas

- O botão vira indicador de progresso sem mudar de largura.
- Após aceitação, a operação recebe ID e aparece no histórico global.
- Jobs e defesas do Grill continuam acompanháveis ao trocar de aba.
- Toast comunica transição; drawer mantém o histórico da sessão.
- Cancelamento só aparece quando a rota existente realmente o suporta.

### Conexão e stale

- Após duas atualizações esperadas sem sucesso: estado **STALE**, preservando os últimos dados.
- Após falha confirmada: estado **OFFLINE**.
- Cada painel mostra “Atualizado há X s”.
- Reconexão usa water; sucesso volta a acid.
- Dados stale não continuam gráficos como se fossem atuais.

### Atalhos

Somente atalhos previsíveis:

- `/`: busca ou filtro principal da tela;
- `Ctrl/Cmd + Enter`: confirmar formulário ou enviar mensagem;
- `Esc`: fechar modal, drawer ou tooltip;
- `?`: abrir ajuda de atalhos.

Sem command palette na primeira migração.

## 6. Responsividade

### Acima de 1100 px

- Sidebar de 216 px.
- Grade de 12 colunas.
- Inspectors laterais permanecem visíveis.
- Chat usa três colunas.
- Workers usa lista mestre e detalhe.
- Tabelas priorizam leitura sem quebrar linhas críticas.

### Até aproximadamente 1100 px

- Sidebar reduzida para 64 px, com ícones, nomes em tooltip e nome acessível.
- Inspectors viram drawers.
- Chat passa a duas colunas; projetos ficam em drawer.
- Status mantém duas colunas quando houver ao menos 900 px úteis; abaixo disso, empilha.
- Matriz Workers preserva primeira coluna e rola horizontalmente.
- Títulos de página caem para 36 px.

### Até aproximadamente 760 px

- Barra superior compacta e navegação em drawer; não usar oito itens em bottom navigation.
- Conteúdo em uma coluna, gutter de 16 px.
- Título de página: 32 px / 2 rem.
- Modais ocupam a tela, com rodapé fixo.
- Listas mestre viram telas anteriores, não colunas estreitas.
- Tabelas mantêm rolagem horizontal e coluna de identificação fixa; só viram linhas empilhadas quando não houver comparação entre colunas.
- Filtros ficam em drawer com resumo dos ativos.
- Alvos interativos têm no mínimo 44×44 px.

## 7. Acessibilidade

Contrastes WCAG calculados sobre as superfícies propostas:

| Cor | Sobre coal | Sobre panel |
|---|---:|---:|
| Bone | 17,82:1 | 16,84:1 |
| Acid | 16,14:1 | 15,25:1 |
| Muted | 8,18:1 | 7,73:1 |
| Gold | 8,90:1 | 8,41:1 |
| Coral | 6,85:1 | 6,47:1 |
| Water | 9,28:1 | 8,77:1 |
| Violet | 5,02:1 | 4,74:1 |

Todas passam AA para texto pequeno. Em fundos preenchidos acid, gold ou coral, usar texto coal; não usar bone sobre essas cores sem nova verificação.

Outras regras:

- Estado nunca depende só de cor: texto, ícone e forma acompanham.
- `focus-visible` water de 2 px em todos os controles.
- Ordem de foco acompanha a ordem visual.
- Modal usa `aria-modal`, prende foco e o restaura ao elemento de origem.
- Toggle usa papel `switch` e nome completo do worker.
- Toast usa região `aria-live="polite"`; falhas críticas usam `assertive`.
- Progresso usa `progressbar` com valor, mínimo e máximo.
- Filas anunciam mudança de posição sem reler a tabela inteira.
- Tooltips usam `aria-describedby` e são acessíveis por foco.
- Chips removíveis possuem botão com nome “Remover papel X”.
- Cabeçalhos e relações de tabela são semânticos.
- Fonte condensada não é usada em parágrafos ou mensagens.
- `prefers-reduced-motion` remove shimmer, transições de deslocamento e animação de sparklines; mudanças permanecem perceptíveis de forma estática.

## 8. Plano de migração aba por aba

**Etapa-base:** aplicar tokens, app shell, modal, drawer, toast/histórico, estados loading/empty/error/stale e deep-links. Não alterar chamadas da API.

1. **Status** — primeiro por ser majoritariamente leitura; valida telemetria, saúde, VRAM, filas, responsividade e reconexão com baixo risco operacional.
2. **Tools** — separa imediatamente ações perigosas da observação e incorpora auth/URL dos servidores MCP.
3. **Workers** — reutiliza tabelas, formulários, drawers e confirmação já estabilizados; adiciona configuração, matriz e auditoria.
4. **Orquestrador** — introduz detalhe navegável, inspector e espera por recurso; mantém os mesmos endpoints de jobs.
5. **Uso/custos** — extrai a visualização já existente no Orquestrador e adiciona filtros/decomposições somente sobre dados disponíveis.
6. **Chat/projetos** — migra o fluxo diário depois de modal, stale e deep-links estarem testados; inclui description e seleção visual ao mover conversa.
7. **Grill Me** — usa os padrões maduros de job longo, filtros, cards de decisão e histórico.
8. **Instruções** — encerra a migração com editor/preview e proteção contra perda, sem dependências sobre as outras áreas.

Cada aba troca apenas apresentação, estado local e navegação. As rotas do control-api e seus contratos permanecem intactos.

## 9. 2–3 direções de mockup

### A. Console editorial equilibrado — recomendada

Sidebar de 216 px, densidade média e cabeçalhos Karvalho fortes. Ornamentos somente em títulos, incidentes e relatório final. É a melhor combinação entre identidade, leitura prolongada e implementação incremental.

### B. Ops compacto

Sidebar de 64 px sempre recolhida, controles de 32 px e predominância de tabelas. Ornamento quase ausente; gold funciona principalmente como grid e divisor. Favorece máxima informação em monitores menores, com menos presença da marca.

### C. Estúdio Karvalho

Sidebar larga, títulos maiores, bandas gold e mais espaço entre regiões. Usa cantos ornamentais também nos painéis principais e alternância acid/coral mais evidente. Tem maior personalidade, mas reduz a quantidade de dados visível sem rolagem.

## 10. Riscos e trade-offs

1. **Acid possui força visual excessiva:** se aplicado a todo estado saudável, pode competir com CTAs. Por isso, superfícies acid preenchidas ficam restritas a ação primária e estado live prioritário.
2. **Gold acumula funções de marca e warning:** a distinção depende obrigatoriamente de ícone, rótulo e contexto, não só da cor.
3. **Bahnschrift Condensed em excesso prejudica leitura:** o sistema limita seu uso a chrome, títulos e valores curtos.
4. **Oito abas aumentam a carga de navegação:** a ordem acompanha frequência e fluxo operacional, mas a sidebar recolhida dependerá de ícones e tooltips bem escolhidos.
5. **A matriz papéis×workers pode crescer muito:** filtros, cabeçalhos fixos e rolagem preservam a comparação, porém projetos grandes continuarão exigindo navegação horizontal.
6. **Mover containers e host para Tools reduz sua visibilidade:** melhora a segurança, mas usuários acostumados ao Status precisarão reaprender onde agir.
7. **Fila global e recortes contextuais duplicam a mesma informação:** qualquer diferença de atualização será perceptível; todas as projeções precisam compartilhar a mesma origem de dados no cliente.
8. **Polling limita a sensação de tempo real:** estados stale e timestamps tornam a limitação honesta, mas não eliminam atrasos entre mudanças.
9. **Histórico local de notificações não é auditoria:** serve à sessão de uso; somente a auditoria fornecida pelas rotas existentes deve ser tratada como registro oficial.
10. **Chat em três colunas exige largura:** a redução progressiva para duas colunas e drawers preserva uso, mas adiciona uma etapa de navegação em laptops.
11. **Coral representa erro e encerramento:** os rótulos “ERRO” e “ENCERRADO”, além dos ícones distintos, são necessários para evitar ambiguidade.
12. **Migração incremental produzirá coexistência visual temporária:** o app shell comum reduz o contraste, mas abas v1 e v2 parecerão diferentes até a conclusão.