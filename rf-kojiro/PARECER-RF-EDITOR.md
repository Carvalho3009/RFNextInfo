# Parecer Técnico — RF Editor (projeto RF Kojiro)

**Repositório:** jpsa13/RF-editor (análise sobre snapshot local `RF-editor-master`)
**Data:** 20/07/2026
**Metodologia:** painel multi-modelo — **Claude Fable 5** (análise principal: 3 agentes de leitura integral do código + verificação manual das alegações críticas), **GPT-5.6-sol** (via Codex CLI, com leitura direta do repositório em disco) e **DeepSeek-R1 32B** (via Ollama local, sobre digest técnico). Toda alegação crítica citada neste parecer foi verificada contra o código-fonte antes de ser incluída.

---

## 1. O que o projeto é hoje

O RF Editor é um app desktop (Electron 42 + React 19 + Vite 8 + TypeScript 6, SQLite via `sqlite3`, SheetJS) que importa as planilhas de dados de um servidor privado de RF Online para um banco SQLite local, permite editá-las numa interface de grid estilo Excel e escreve as alterações de volta nos arquivos `.xlsx` originais.

**Funcionalidades entregues e funcionais:**

O app tem quatro views (Itens, Dicionário de Efeitos, HGK/CSV e ItemCombine com modos receitas/grupos/planilha), um grid editável completo (edição inline, undo/redo, copiar/colar TSV, seleção de intervalo, filtros por coluna com valores sob demanda, redimensionamento e auto-fit de colunas, paginação 200/500/1000, preview de ícones), o Box Builder para BoxItemOut (autocomplete de itens, validação de civil, normalização de chances para 10000, replicação automática por raça acc/bell/cora), templates de loot por boss com escopo mapa/raça e conversão automática entre raças, importação de Excel/CSV/pasta inteira/bosses (.txt/.ini) com barra de progresso, detecção de planilha alterada externamente (mtime), backup automático antes de toda escrita com restauração por fonte, perfis multi-banco (ex.: "Woods") e quatro geradores de weapon socket combines com escrita de volta em CombineTable2.xlsx/LinkedCombines.xlsx.

**Números do código (11.487 linhas relevantes):** `src/App.tsx` com 6.582 linhas num único componente (88 `useState`, 29 `useEffect`, 20 `useMemo`, **zero** `useCallback`, ~107 funções internas); `electron/main.cjs` com 2.239 linhas e 34 canais IPC; `electron/services/database.cjs` com 2.511 linhas e uma tabela `items` "wide" (15 colunas fixas + `extra_01..extra_160`).

---

## 2. Avaliação consolidada do painel

| Modelo | Nota | Síntese |
|---|---|---|
| **Claude Fable 5** | 6,5/10 como ferramenta interna; 3/10 como produto finalizável no estado atual | O ativo mais valioso é o conhecimento de domínio codificado (civil, raças, chances, BoxItemOut, backups). O passivo é estrutural: monolito, sem build de produção, modelo de dados sem semântica. |
| **GPT-5.6-sol** | 6,5/10 (8 como ferramenta pessoal; 4 como entregável; 3 como base direta do site; 8 como fonte de dados com camada de publicação) | Protótipo interno avançado com valor real; `App.tsx` é sintoma, o problema é acoplamento sem testes protegendo contratos. O SQLite atual é área de ingestão, não database semântica. |
| **DeepSeek-R1 32B** | 5/10 | Base funcional com recursos significativos, mas acoplamento, ausência de testes e vulnerabilidades tornam manutenção e evolução difíceis. |

**Convergência total dos três modelos em:** (a) o app funciona e o domínio embutido não deve ser jogado fora; (b) não existe build de produção — isso é o item nº 1 de "finalizar"; (c) o monolito App.tsx e a ausência de testes são o maior risco de manutenção; (d) o site NÃO deve nascer do código do desktop — deve nascer dos dados, via camada de publicação; (e) as vulnerabilidades (path traversal no restore de backup, sem CSP) precisam ser fechadas antes de qualquer release.

**Pontos fortes confirmados:** backups automáticos antes de toda escrita; WAL + transações serializadas + prepared statements + FK cascade; allow-lists nos filtros dinâmicos (sem SQL injection explorável); `contextIsolation: true` + `nodeIntegration: false`; proveniência preservada (`source_file`, `excel_row`, `source_columns`) — matéria-prima excelente para a fase site.

---

## 3. Defeitos confirmados (verificados no código)

1. **Não existe build de produção.** `main.cjs:460` faz `loadURL("http://localhost:5173/...")` incondicionalmente; não há `loadFile`, `app.isPackaged`, electron-builder nem forge. Hoje o app só roda com `npm run dev:electron` na máquina do desenvolvedor. *(verificado)*
2. **Bug de multiplicação de linhas no boss/mapa** *(achado do GPT-5.6-sol, confirmado por leitura)*: em `listItems` (database.cjs ~1214-1224) há um `LEFT JOIN boss_monsters` adicional **após** a subquery agregada `boss_maps` — quando um boss existe em N mapas, cada linha de itemlooting é multiplicada por N, inflando o `COUNT` (total da paginação) e duplicando linhas no resultado.
3. **Path traversal em `restore-source-backup`** (main.cjs ~83): `backupName` vindo do renderer entra em `path.join(BACKUP_ROOT, baseName, backupName)` sem sanitização — `../` escapa do diretório de backups e permite copiar arquivo arbitrário sobre a planilha. *(verificado)*
4. **Virtualização praticamente morta** *(achado do GPT-5.6-sol, consistente com a leitura dos agentes)*: página máxima é 1.000 linhas, mas a virtualização só ativa acima de 1.200 (ou 250 com ícones) — na prática, até 1.000 linhas × ~178 colunas renderizam sem virtualização, com zero `useCallback`/`React.memo`.
5. **`items.id` não é identidade estável**: reimportar apaga e reinsere a fonte inteira (AUTOINCREMENT muda) — não pode ancorar URLs públicas nem sincronização.
6. **13 pontos de erro engolido** (10 `catch {}` + 3 `.catch()` vazios) no renderer, mais o padrão `.catch(() => false)` no main — falhas de importação/escrita somem sem feedback.
7. **Higiene**: 3 painéis stub "Em breve" (Gearscore, Gemas, Transmog); painel de filtros avançados completo mas desligado (`SHOW_FILTER_PANEL = false`, App.tsx:122); handler `test` e `getBestImportSheetName` mortos; marcadores de debug (LIVE-CODE-MARKER); 7 strings com mojibake ("AÃ§Ãµes"); `rfloot.db-wal`/`-shm` versionados no repo enquanto só `*.db` está no .gitignore; ícones dependem de `process.cwd()`.
8. **Duplicação**: 4 geradores de combine ~95% idênticos; cópia de DB de perfil em 3 lugares; blocos de JOIN triplicados; detecção numérica em 3 lugares.
9. **Sem testes, sem CI, sem versionamento de schema** (migração "convergente por boot", sem `PRAGMA user_version`).

---

## 4. PARECER — O que fazer para finalizar

A recomendação unânime do painel: **tratar o desktop e o site como dois produtos.** O desktop é o *editor* (ferramenta de autoria, 1-3 usuários técnicos); o site é o *viewer* público. "Finalizar o projeto" significa: (F1) tornar o editor um app distribuível e confiável, e (F2-F3) construir a database linkada como camada nova ao lado dele — não reescrever o editor.

### Fase 0 — Correções críticas (1 semana de esforço)

1. Corrigir o JOIN duplicador de boss/mapa em `listItems`/`listItemColumnValues` (remover o `LEFT JOIN boss_monsters` redundante — a subquery `boss_maps` já agrega).
2. Sanitizar `backupName` (`path.basename` + verificação de que o caminho resolvido permanece dentro de `BACKUP_ROOT`).
3. Adicionar CSP e bloquear navegação/abertura de janelas externas (checklist oficial do Electron).
4. Corrigir `.gitignore` (`*.db-wal`, `*.db-shm`) e remover os binários do repo.
5. Trocar `catch {}` críticos (perfil, importação, backup, escrita Excel) por log + toast de erro; os de leitura opcional de localStorage podem continuar silenciosos.

### Fase 1 — Tornar distribuível (1-2 semanas)

6. Electron Forge (ou electron-builder) com alvo Windows x64; `app.isPackaged` decidindo entre `loadURL` (dev) e `loadFile(dist/index.html)` (produção); rebuild do `sqlite3` para a ABI do Electron (ou migração para `better-sqlite3`, mais simples de empacotar e mais rápido).
7. Mover perfis, bancos, backups e settings de `__dirname` para `app.getPath("userData")` — dentro do asar é somente leitura.
8. Versionamento de schema com `PRAGMA user_version` + migrações sequenciais com backup pré-migração.
9. Higiene de release: remover stubs "Em breve" (ou escondê-los atrás de flag), handler `test`, marcadores de debug, mojibake; decidir o destino do painel de filtros (ligar ou apagar); README real com instalação e localização dos dados.
10. Política de retenção de backups (ex.: últimos 30 por arquivo).

### Fase 2 — Rede de proteção e performance (2-3 semanas, pode intercalar com a Fase 3)

11. Suíte mínima de testes de contrato (Vitest) sobre o que quebra de verdade: importação de fixture, reimport, escrita apenas na aba/células pretendidas, soma 10000 do BoxItemOut, conversão de raça, parse de combines, restore de backup, COUNT sem duplicação. Sem testes de componente React por enquanto.
12. Sequenciador de requisições no `loadItems` (contador em `useRef`) para resposta antiga não sobrescrever a nova.
13. IPC em lote `get-items-by-codes(codes[])` substituindo resoluções sequenciais de meta de item.
14. Virtualização por células (linhas × colunas visíveis), não por linhas; extração gradual do App.tsx em fatias verticais (items-grid, imports, profiles, effects, boxes, combines) — sem reescrita total e sem Redux (estado local + fatias resolve).
15. Unificar os 4 geradores de combine num gerador parametrizado; extrair serviços puros do main.cjs (backup, excel-reader, excel-writer, profiles).

### Fase 3 — A database linkada e o site (o objetivo do criador)

**Decisão de arquitetura (consenso do painel):** o site não consulta nem recebe cópia do `rfloot.db`. O fluxo é:

```
Excel/CSV → SQLite de ingestão (editor, como hoje)
→ materializador canônico (novo)
→ snapshot versionado (rf-dataset-<realm>-<versão>)
→ validação/diff → publicação atômica → site somente leitura
```

16. **Registro explícito de fontes** no editor: cada `source_file` ganha um `sourceType` declarado (`items | monsters | drops | shops | recipes | boxes`) com mapeamento das colunas semânticas (qual `extra_N` é o código do monstro, qual é a chance...). Isso substitui as regex de nome de arquivo e é o pré-requisito de tudo.
17. **Materializador**: SQL que traduz a tabela wide em entidades nomeadas — `items`, `monsters`, `maps`, `drop_entries`, `shops/shop_items`, `recipes/recipe_inputs/outputs`, `loot_boxes/entries`, `effects` — cada relação carregando `dataset_id` + fonte/aba/linha de origem (rastreabilidade até a planilha). Identidade pública = `realm + entity_type + code` (nunca `items.id`; auditar colisões de código entre arquivos antes).
18. **Site**: Next.js App Router + TypeScript. Banco: PostgreSQL (+ `pg_trgm` para busca) se houver backend; alternativa mais barata defendida pelo Fable para o primeiro release: snapshot SQLite servido estaticamente com build SSG do Next (sem servidor de banco — cabe em Vercel/Cloudflare Pages; migra para Postgres quando precisar de busca pesada ou atualizações frequentes). Rotas: `/items/[slug]`, `/monsters/[code]`, `/maps/[slug]`, `/recipes/[code]`, `/search`. Página de item com as relações inversas: *dropa de, vendido por, ingrediente de, produzido por, contido em box, variantes por raça, efeitos*.
19. **Publicação**: editor exporta `rf-dataset-<realm>-<versão>.zip` (manifest + dados canônicos + ícones PNG por hash + checksums); painel autenticado importa como novo `dataset_id`, roda validadores, mostra diff contra a versão publicada e troca um único ponteiro (`realms.current_dataset_id`) — rollback = voltar o ponteiro. Nunca sincronizar `.db`/`-wal`/`-shm` com o editor aberto.
20. **Reencarnação dos stubs**: Gearscore/Gemas/Transmog fazem mais sentido como páginas do site (calculadoras públicas sobre a database linkada) do que como painéis do editor.

### Novas funcionalidades recomendadas para o editor (além das fases)

- **Tela "Diagnóstico da fonte"** (quick win de alto valor): códigos duplicados, referências não resolvidas, chances inválidas, ícones ausentes, combine sem material/resultado, boss sem mapa — vira o validador do pipeline de publicação.
- **Preview antes de salvar no Excel**: células afetadas, abas, backup criado.
- **Diff planilha atual × última importação** (o watch de mtime já detecta a mudança; falta mostrar o quê mudou).
- **Log de operações** com horário/arquivo/aba/etapa (substitui os erros engolidos).
- **Exportação JSON/CSV** de visões filtradas (sugestão DeepSeek — barata e útil).

---

## 5. Riscos e armadilhas do caminho

1. **Ligações falsas na database linkada** — igualdade de texto/posição `extra_N` não basta; cada fonte precisa de semântica declarada e exemplos confirmados (motivo do item 16 vir primeiro).
2. **Fonte da verdade ambígua** — definir: Excel gravado + reimport validado é a origem; drafts do grid nunca são publicáveis.
3. **Publicar o perfil errado** — snapshot declara `realm/profile` e a confirmação mostra em destaque.
4. **Publicação parcial** — nunca atualizar tabelas públicas uma a uma; sempre dataset novo + troca de ponteiro.
5. **Over-engineering prematuro** (alerta dos três modelos): sem Neo4j, sem GraphQL, sem Redis, sem microserviço de busca no primeiro release. Começar pelas 4 relações de maior valor: drops, boxes, recipes, shops.
6. **Reescrita total paralisando o projeto** — o editor continua funcionando durante todas as fases; o materializador nasce ao lado, não no lugar.
7. **Busca do site repetindo o erro do desktop** — nada de `LIKE '%x%'` sobre 160 colunas; campos canônicos indexados.

---

## 6. Resumo executivo

O RF Editor cumpriu as fases 1 e 2 da visão do criador (editar loot → editar tudo) com uma profundidade de domínio rara em projetos desse tipo — backups, civil, raças, chances, combines. Para a fase 3 (database linkada no site), o painel é unânime: **não é o app que vira site; são os dados que ganham uma camada de publicação.** Finalizar = Fase 0 (bugs/segurança, ~1 semana) + Fase 1 (instalador real, 1-2 semanas) fecham o desktop como produto; Fase 2 protege contra regressão; Fase 3 entrega a visão do site com snapshots versionados, mantendo o editor vivo como ferramenta de autoria. Esforço total estimado para chegar ao site no ar com drops/boxes/recipes/shops linkados: **6 a 10 semanas** de trabalho consistente, sem reescrever o que já funciona.

---

*Análises completas dos três modelos disponíveis nos anexos do job #305 do orquestrador MCP (gpt-5.6-sol e deepseek-r1:32b) e nos relatórios dos agentes de exploração (Fable).*
