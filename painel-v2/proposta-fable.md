Segue a proposta de design completa. Não precisei de ferramentas — todo o insumo está no brief; os valores de contraste citados na seção 7 foram calculados a partir dos hex fornecidos.

---

# Proposta de Design — MCP Control v2 (identidade Karvalho)

## 1. Conceito

**"Sala de máquinas com moldura editorial: o ornamento vive na casca, o dado vive nu."**

Princípios:
1. **Ornamento decai com a profundidade.** Nível 0 (navegação, cabeçalho de aba, banda de sistema) recebe a linguagem Karvalho completa — molduras gold com cantos ornamentais, display condensado, linhas convergentes. Nível 1 (cards de conteúdo) recebe borda gold simples. Nível 2 (linhas de tabela, células, chips) recebe zero ornamento.
2. **Acid é escasso.** É CTA, estado "vivo" e link — nunca preenchimento de área grande. O que é raro chama atenção; o que é abundante cansa.
3. **Perigo tem geografia.** Ações destrutivas nunca coabitam com telemetria: vivem em zonas demarcadas por coral e exigem modal próprio.
4. **Nunca travar em silêncio.** Todo estado de espera (VRAM, lock, fila) tem posição visível e ancestral clicável.
5. **Uma verdade global, oito vistas.** VRAM, fila de recursos e saúde da conexão são cromo persistente, não conteúdo de aba.

---

## 2. Arquitetura de informação

### Navegação: sidebar lateral esquerda fixa

- **Largura 220px** (colapsa para 64px, ver §6). Fundo `--coal`, borda direita 1px `rgba(212,166,77,.45)`.
- 8 itens em `--display` uppercase 13px, letter-spacing 0.06em. Item ativo: texto `--acid` + barra esquerda 3px `--acid`. Hover: texto `--bone`. Badge numérico à direita do item quando há pendência (jobs rodando no Orquestrador, perguntas abertas no Grill Me) — pílula 16px `--gold` texto `--coal`.
- Justificativa vs. topo: 8 abas + badges + logotipo não cabem confortavelmente numa barra horizontal a 1100px, e o tipo condensado vertical é assinatura do site.

**Ordem (frequência de uso, operação primeiro):**
1. **Status** 2. **Workers** 3. **Orquestrador** 4. **Chat** 5. **Grill Me** 6. **Tools** 7. **Uso & Custos** 8. **Instruções**

### Banda de sistema (nova, global)

Faixa de 40px no topo de todas as abas, fundo `--panel`, borda inferior gold translúcida. Conteúdo, da esquerda para a direita:
- **VRAM (§3.4):** barra horizontal 120px com valor `8.2/12 GB` em mono; ao lado, contador `aguardando_vram: 2` como link — clique abre o drawer da fila.
- **Fila de ações (§3.6):** ícone + contador `fila: 3`. Clique abre **drawer lateral direito (380px)** listando: recurso, dono atual (link para job/conversa), quem espera com posição, prioridade como chip (`interativa`=acid, `normal`=bone, `batch`=violet). O drawer é global — a fila afeta todas as abas, então não pertence a nenhuma.
- **Conexão:** ponto de estado + timestamp (`ao vivo` acid / `dados de 12s atrás` gold / `offline — reconectando` coral, ver §5).
- **Sino de toasts** com histórico (ver §3).

### Promoções, rebaixamentos, realocações

| Movimento | O quê |
|---|---|
| Promove | Workers sai de dentro de Status → aba própria; Uso sai do Orquestrador → aba própria; VRAM/fila sobem para cromo global |
| Rebaixa | Containers Docker e comandos de host descem para zona "Operações" dentro de Status, atrás de demarcação de perigo |
| Cria | Grill Me (F4); configuração de auth de servidor MCP dentro de Tools (endpoint `PUT .../auth` já existe) |
| Auditoria | Vive em Workers: linha de rodapé por card + drawer de histórico por worker (ver §4) |

### Deep-links e breadcrumbs

Roteamento por hash, sem mudança de API: `#/status`, `#/workers/{id}`, `#/orquestrador/jobs/{id}`, `#/chat/{projeto}/{conversa}`, `#/grill/{sessao}`. Breadcrumb em todo detalhe: `ORQUESTRADOR / JOBS / #4127` em `--display` 12px, segmentos anteriores `--muted` clicáveis, atual `--bone` — resolve o débito "sem breadcrumb no job".

---

## 3. Sistema de design

### Tipografia

| Nível | Fonte | Tamanho | Uso |
|---|---|---|---|
| H1 aba | `--display` | 28px / lh 0.95, uppercase, com `<span>` coral numa palavra | Título da aba (único elemento "editorial grande") |
| H2 card | `--display` | 16px / lh 1.1, uppercase, cor `--gold`, letter-spacing 0.08em | Título de card |
| Label | `--display` | 11px, uppercase, `--muted`, letter-spacing 0.1em | Rótulos de campo, th de tabela |
| Corpo | `--body` | 14px / lh 1.45, `--bone` | Texto geral, chat |
| Secundário | `--body` | 13px, `--muted` | Metadados, timestamps |
| Dados | `--mono: "Cascadia Mono", Consolas, monospace` (novo token) | 13px | Números, IDs, tokens, custos, VRAM — alinhamento tabular |

Escala editorial do site (headings enormes) **não** entra no miolo: só o H1 da aba a mantém, reduzida de ~64px do site para 28px.

### Espaçamento e forma

- Escala 4px: `4 / 8 / 12 / 16 / 24 / 32 / 48`. Padding de card: 16px; gap entre cards: 16px; padding de célula de tabela: 8px 12px (denso).
- **Raio 2px em tudo** (a identidade é angular; nada de cantos redondos).
- **Molduras:** card nível 1 = borda 1px `rgba(212,166,77,.45)` + cantos ornamentais 12×12px/2px `--gold` (sup-esq, inf-dir) **apenas** no primeiro card de cada aba e em modais. Demais cards: borda simples, sem cantos.

### Mapeamento de tokens para papéis de dashboard

| Papel | Token | Regra |
|---|---|---|
| ok / live / ligado | `--acid` | Sempre ponto/texto/traço — nunca preenchimento de área |
| warn | `--gold` | **Sempre acompanhado do ícone ▲** (gold também é cor estrutural; o ícone desambigua) |
| err / parado / destrutivo | `--coral` | |
| info / focus | `--water` | |
| batch / categoria extra | `--violet` | Prioridade batch na fila, categorias do Grill Me |
| Barra de progresso | trilho `rgba(244,242,235,.08)`; preenchimento `--acid` → `--gold` >75% → `--coral` >90% | Mantém thresholds atuais; altura 6px |
| Sparkline | linha `--acid` 1.5px, preenchimento gradiente acid 10%→0; muda para gold/coral quando o valor atual cruza threshold | Canvas 60 pontos como hoje |
| Badge on/off | on: ponto acid + texto bone; off: ponto `--muted` + texto muted | Ponto 6px, nunca só cor |
| Status de tabela | live=`--acid`, encerrado=`--coral` (padrão do site) | |

### Componentes-chave

- **Card:** 3 variantes — `framed` (moldura + cantos, nível 0/1 de destaque), `plain` (borda gold .45), `inset` (fundo `rgba(244,242,235,.03)`, sem borda, para sub-blocos).
- **Tabela:** bordas horizontais `rgba(212,166,77,.25)`, th em Label gold, hover de linha `rgba(212,166,77,.06)`, números em `--mono` alinhados à direita. Scrollbar gold.
- **Modal (substitui alert/confirm/prompt):** overlay `rgba(7,9,9,.8)`; caixa `--panel`, moldura framed, largura 440px (560px para formulários). Variante **danger**: título coral, botão de confirmação coral preenchido, e para as duas ações de maior risco (parar container do painel, comando de host destrutivo) campo "digite o nome para confirmar". Focus trap + Esc fecha.
- **Toast com histórico:** bottom-right como hoje, 4s, borda esquerda 3px na cor do tipo; sino na banda de sistema abre drawer com os últimos 50, com timestamp — resolve "toasts somem sem histórico".
- **Chips de papéis:** pílula 22px, `--display` 11px uppercase. Permitido: borda acid, texto acid. Proibido: borda coral, texto coral, prefixo `⊘`. Herdado do padrão global: borda muted tracejada.
- **Toggle:** 40×20px, trilho `rgba(244,242,235,.15)`, ligado: trilho acid, knob coal. `role="switch"`.
- **Tooltip:** fundo `--panel`, borda 1px gold, 13px, delay 300ms; variante "temperatura" com régua (ver §4 Workers).
- **Skeleton:** blocos `rgba(244,242,235,.06)` com shimmer sutil (desligado em reduced-motion). Substitui strings cruas de estado vazio.
- **Estado vazio:** ícone da seção em gold .3 + frase em `--muted` + CTA quando aplicável ("Nenhum job. **Criar orquestração →**" em acid com seta, padrão text-link do site).
- **Filtros:** botões de texto com border-bottom 2px acid quando ativos (padrão do site), usados em Grill Me, Uso e histórico de jobs.
- **Banda invertida** (fundo gold, texto coal): reservada a um único uso por tela — o alerta máximo (ex.: "relatório pronto" no Grill Me, "GPU saturada" no Status).

### Estados

hover: borda do card sobe para `rgba(212,166,77,.7)`; focus: outline 2px `--water` offset 2px (universal); disabled: opacidade .4 + `cursor:not-allowed`; loading: skeleton (conteúdo) ou spinner 14px no botão (ação); error: card inset com borda esquerda coral + mensagem + botão "tentar de novo"; **stale:** ver §5.

---

## 4. Especificação por aba

### 4.1 Status (telemetria + zona de operação)

- **Layout:** grid 2 colunas `2fr 1fr`. Coluna A: card framed "Hardware" (CPU/GPU com sparklines lado a lado, VRAM em barra grande com fila `aguardando_vram` listada abaixo — versão expandida do widget da banda), card "Servidores MCP" (tabela: nome, ponto de saúde via `GET /api/health` que hoje não é usado, latência). Coluna B: card "Containers" e card "Comandos de host".
- **Zona de operação:** Containers e Comandos ficam sob um sub-cabeçalho `OPERAÇÕES` com linha separadora coral .4. Botões de parar/executar são ghost coral; parar o container do próprio painel usa modal danger com digitação de nome. Resolve o débito "destrutivo a um confirm de distância".
- **Muda vs. hoje:** workers saem daqui; ações perigosas demarcadas; health check novo; estado stale por card (timestamp da última leitura).

### 4.2 Workers (§3.5 completo — detalhe extra)

- **Layout:** cabeçalho com seletor de vista `Cards | Matriz` (filtro de texto do site) + seletor de projeto (para overrides). Vista Cards: grid 2 colunas de cards `plain`, um por worker.
- **Card de worker:**
  - Linha 1: nome em H2, badge de tipo (`OLLAMA` violet / `CLI` water), **toggle liga/desliga** à direita.
  - Linha 2: chips de papéis — permitidos (acid) e proibidos (coral, `⊘`). Botão `+` abre popover com a lista de perfis para alternar permitido/proibido/neutro. **Tooltip de temperatura** ao hover no chip do papel: régua horizontal 0→1 com marcador na faixa do papel e legenda ("juiz 0–0.2 · … · interrogador 0.9+"), faixas em gradiente water→coral.
  - Linha 3: grade 4 colunas de limites em `--mono` com edição inline (clique → input + ✓/✕): **concorrência máx · tokens/job · tokens/dia · keep_alive**. Tokens/dia mostra barrinha de consumo do dia sob o valor.
  - Rodapé (auditoria): 12px muted — `v12 · alterado por owner em 14/07 14:32` — clicável, abre **drawer de histórico** com diffs por versão (campo, valor anterior → novo, quem, quando) e botão "restaurar esta versão".
- **Vista Matriz (papéis×worker por projeto):** tabela com papéis nas linhas, workers nas colunas. Célula: `✓` acid (permitido), `⊘` coral (proibido), `·` muted (herdado do global). Com projeto selecionado, override tem sublinhado gold; clique na célula cicla herdado→permitido→proibido; barra fixa inferior "3 alterações pendentes — **Aplicar** / Descartar" (aplicar em lote, um toast por resultado).
- **Muda vs. hoje:** tudo — a aba não existia; toggles, limites e matriz eram inexistentes ou implícitos.

### 4.3 Orquestrador

- **Layout:** coluna esquerda 340px fixa (lançador: tipo de job, modelo/perfil, prompt) + direita fluida (jobs ativos no topo como cards `inset` com progresso, histórico em tabela abaixo com filtros de texto por tipo/estado).
- **Detalhe de job:** rota `#/orquestrador/jobs/{id}` com breadcrumb; progresso por etapa; `<details>` para raciocínio/JSON mantidos, reestilizados (summary em Label gold). Job em `aguardando_vram`/`aguardando_recurso` mostra chip gold "▲ na fila · posição 2" clicável → abre o drawer global da fila com a linha dele destacada.
- **Muda vs. hoje:** tabela de uso sai (vai para Uso & Custos); breadcrumb novo; espera nunca é silenciosa.

### 4.4 Chat / Projetos

- **Layout:** 3 colunas — projetos (200px), conversas (260px), thread (fluida, máx. 860px).
- Criar projeto: modal com nome + **descrição** (o `POST /api/projects` já aceita e a UI não coleta); descrição vira subtítulo muted no cabeçalho do projeto.
- **Mover conversa:** menu kebab da conversa → modal com dropdown de projetos — mata o `prompt()` de slug.
- Conversa em `aguardando_recurso`: banner gold no topo da thread "▲ aguardando {recurso} · posição 3 · dono atual: job #4127" (dono clicável). Mensagem em geração: cursor pulsante acid (estático em reduced-motion).
- **Muda vs. hoje:** modal de mover, descrição de projeto, banner de fila, polling de 2s mantido.

### 4.5 Grill Me (detalhe extra)

- **Layout:** coluna única centrada, máx. 720px (leitura, não densidade). Cabeçalho: H1 + barra de progresso "12 de 30 tratadas" + botão **Finalizar** (primário acid).
- **Filtros:** linha de botões de texto por categoria (border-bottom acid quando ativo; cor da categoria pode usar violet/water/gold como acento) + chips de severidade (alta coral / média gold / baixa water).
- **Card de pergunta:** borda esquerda 4px na cor da severidade; texto da pergunta em corpo 15px; contexto/citação em bloco `inset`; rodapé com 4 ações:
  1. **Responder** (primário acid) → textarea inline expande no próprio card;
  2. **Defender com agente** (ghost gold) → popover de seleção de perfil, dispara job e o card entra em estado "agente defendendo…" com spinner e link para o job;
  3. **Aceitar risco** (ghost coral) → exige justificativa de 1 linha antes de confirmar;
  4. **Descartar** (text-link muted).
- Card tratado colapsa para uma linha (pergunta truncada + badge da resolução: respondida acid / defendida water / risco aceito coral / descartada muted), expansível.
- **Finalizar:** modal de confirmação com resumo por resolução → gera relatório; quando pronto, **banda invertida gold** no topo: "RELATÓRIO PRONTO — **ver →**" (relatório em markdown renderizado, rota própria com breadcrumb).

### 4.6 Tools

- **Layout:** 2 colunas — lista de servidores/tools (300px) + área de trabalho.
- Card de servidor MCP ganha kebab com: **Editar URL** (o `PATCH` já aceita `url`) e **Configurar credenciais** (`PUT .../auth`) — modal de formulário 560px com campos mascarados e aviso de que valores salvos não são reexibidos.
- Form de JSON Schema mantido, reestilizado (labels em Label, inputs fundo `--coal` borda gold .45, focus water); resultado em markdown num card `inset`.

### 4.7 Uso & Custos (detalhe extra)

- **Layout:** linha de 4 stat tiles (custo hoje / 7 dias / mês / tokens do dia — valor em `--mono` 24px bone, delta em 12px acid▼/coral▲, rótulo em Label) → sparkline de custo diário (30 dias, largura total, linha gold) → tabela por modelo/provedor (bordas gold, colunas: modelo, chamadas, tokens in/out, custo, % do total com microbarra) → tabela por projeto.
- **Filtros de período** como botões de texto: `HOJE · 7D · 30D · TUDO`.
- **Muda vs. hoje:** promovida de sub-seção do Orquestrador a aba; ganha tiles e visão por projeto (mesmos dados, novas agregações no front).

### 4.8 Instruções

- Coluna única máx. 860px, TOC fixa à direita (180px, some <1100px), markdown com h2/h3 em `--display`, código em `--mono` sobre `--panel`, links no padrão acid+seta. Único lugar onde a escala editorial pode respirar (h2 de 22px).

---

## 5. Padrões de interação

- **Destrutivas — 3 níveis:** (a) reversível (desligar worker): toggle direto + toast com "desfazer" de 5s; (b) disruptiva (parar container comum, matar job): modal danger com frase de consequência; (c) crítica (container do painel, comando de host mutável): modal danger + digitação do nome do alvo. Comandos de host mostram o comando literal em `--mono` dentro do modal antes do OK.
- **Longa duração:** todo job/geração tem progresso no local de origem + badge no item da sidebar; ao concluir, toast persistente (não expira até clique) com link profundo para o resultado.
- **Conexão/stale:** indicador da banda com 3 estados — `ao vivo` (acid) quando o último poll respondeu; `dados de Xs atrás` (gold, com contador) quando >2 intervalos sem resposta, e os cards ficam com opacidade .7; `offline` (coral) após 3 falhas, com backoff exponencial e botão "reconectar agora". Nenhum dado some — só envelhece visivelmente. Resolve "sem estado stale/reconexão".
- **Login:** tela com moldura framed, campo de token mascarado, sem exibir caminho do arquivo (mensagem de ajuda genérica "token do operador").
- **Atalhos:** `Alt+1..8` troca de aba; `Esc` fecha modal/drawer; `/` foca o filtro da aba atual; `f` abre o drawer da fila. Discreto: legenda no rodapé da sidebar expandida.

---

## 6. Responsividade (desktop-first)

- **≥1440px:** tudo conforme especificado; conteúdo máx. 1600px centrado.
- **≤1100px:** sidebar colapsa para 64px (só ícones + badges; tooltip com o nome); grids de 2 colunas viram 1 coluna com a coluna estreita (lançador do Orquestrador, listas do Tools) virando seção colapsável no topo; TOC de Instruções some; banda de sistema mantém tudo, comprime rótulos.
- **≤760px:** coluna única geral; banda vira só ícones + contadores (drawer continua sendo a vista completa); tabelas largas (uso, jobs) ganham scroll horizontal com scrollbar gold e primeira coluna fixa; no Chat, as 3 colunas viram navegação empilhada (projetos → conversas → thread, com breadcrumb de volta). Uso real é desktop — 760px é degradação digna, não alvo.

---

## 7. Acessibilidade

Contrastes calculados (WCAG 2.1) sobre `--coal`/`--panel`:

| Par | Razão | Veredito |
|---|---|---|
| bone / coal | ~17,8:1 | AAA |
| acid / coal | ~15,9:1 | AAA (texto pequeno ok) |
| muted / coal · / panel | ~8,4:1 · ~8,2:1 | AAA — melhora o débito de contraste atual |
| gold / coal | ~8,8:1 | AAA |
| water / coal | ~9,2:1 | AAA |
| coral / coal · / panel | ~6,8:1 · ~6,4:1 | AA (AAA para ≥18px) |
| coal / acid (botão) · coal / gold (banda) | ~15,9:1 · ~8,8:1 | AAA |
| **borda gold .45 / coal** | **~2,5:1** | **Reprova 3:1 de componente de UI** → alpha .45 só para bordas decorativas; componentes interativos (inputs, toggles, células clicáveis da matriz) usam **.65** (~4:1) |

- Acid vs. gold são próximos para visão deutan: warn sempre com ▲, err com ✕/⊘, ok com ponto — forma redunda cor em todos os semáforos.
- `focus-visible` water 2px universal (já é padrão do site). Modais com focus trap e `aria-modal`. Toggles `role="switch"` + `aria-checked`. Toasts em `aria-live="polite"`; erros de conexão em `aria-live="assertive"`. Sidebar como `<nav>` + `aria-current="page"`. Matriz papéis×worker: células como botões com `aria-label` completo ("juiz em ollama-1: permitido, override do projeto X"). Polling não anuncia atualizações rotineiras (evita ruído de leitor de tela).
- `prefers-reduced-motion`: sem shimmer, sem animação de sparkline, cursor de geração estático, transições de drawer viram corte seco.

---

## 8. Plano de migração aba por aba

Pré-etapa: **casca** — tokens CSS, componentes (card/modal/toast/tabela), sidebar, banda de sistema, roteamento por hash. As abas antigas continuam funcionando dentro da casca nova (o show/hide atual é compatível).

1. **Instruções** — quase estática; valida casca, tipografia e markdown com risco zero.
2. **Status** — valida telemetria (sparklines, barras, stale) e o padrão de zona de perigo; é a aba mais vista, dá retorno imediato.
3. **Workers** — aba nova, sem legado para quebrar; destrava o requisito §3.5 cedo.
4. **Uso & Custos** — extração de dados que já chegam ao front; baixo risco, reduz o Orquestrador antes de mexer nele.
5. **Tools** — inclui as UIs novas de auth/URL (endpoints já existem); form de JSON Schema é o maior trabalho de reestilo.
6. **Orquestrador** — já emagrecido pelo passo 4; migra lançador, detalhe de job e integração com a fila.
7. **Chat** — por último entre as existentes: polling de 2s, estado persistente e maior custo de regressão no uso diário.
8. **Grill Me** — depende da maturidade do F4 no backend; ir por último evita retrabalho de design sobre contrato instável.

Nenhum passo altera rota; cada aba migrada é um deploy independente.

---

## 9. Direções de mockup

**A — Editorial pleno.** Sidebar 220px, moldura ornamental em todos os cards nível 1, H1 36px com span coral, banda invertida usada com generosidade. Máxima identidade Karvalho; a mais bonita em screenshot, a mais pesada em uso de 8h.

**B — Austero operacional.** Corpo 13px, padding de card 12px, ornamento só no H1 da aba e nos modais; navegação por abas no topo (economiza 220px horizontais para as tabelas). Karvalho como tempero, densidade como prato.

**C — Híbrido comando** *(recomendada — é a especificada acima)*. Sidebar colapsável, ornamento decaindo com profundidade, abas "vitrine" (Status, Grill Me) mais editoriais e abas "bancada" (Workers, Uso) mais densas. Meio-termo deliberado.

---

## 10. Riscos e trade-offs

1. **Gold com função tripla** (estrutura, warn, banda invertida) pode diluir o sinal de alerta mesmo com o ícone ▲ — se em teste real o warn se perder, o fallback é reservar gold só para estrutura e adotar âmbar deslocado (ex.: `#e0a458` do tema antigo) para warn, ao custo de pureza da paleta.
2. **Acid é agressivo em uso prolongado** em sala escura; mesmo racionado, sparklines + toggles + links acid numa tela densa podem saturar. Mitigação prevista (acid nunca em área), mas só protótipo confirma.
3. **Bahnschrift condensado uppercase em th e labels** custa legibilidade em varredura rápida de tabelas densas, e o fallback Arial Narrow (fora do Windows) degrada bastante o desenho — a identidade fica refém da plataforma.
4. **Sidebar consome 220px** que hoje as abas de 2 colunas usam; a 1366px de largura útil o colapso para 64px vira o estado normal, e a navegação por ícones exige memorização.
5. **Banda de sistema global duplica dados do Status** e adiciona um consumidor permanente de polling em todas as abas; se o custo perceptível de atualização incomodar, terá que degradar para atualizar só a cada 10s fora do Status.
6. **Modal com digitação de nome** para ações críticas protege, mas irrita um usuário único e experiente que para containers todo dia; o nível (b) vs. (c) da escala de §5 pode precisar de recalibragem após uso real.
7. **Roteamento por hash + drawers + matriz editável em lote** elevam bastante a complexidade do JS vanilla atual; sem disciplina, o v2 recria o problema dos "dezenas de style inline" em forma de espaguete de estado.