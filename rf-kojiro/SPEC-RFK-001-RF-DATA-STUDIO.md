# SPEC-RFK-001 — RF Data Studio: Arquitetura e Fases

**Status:** proposta para aprovação do owner (Carlos)
**Autor:** GPT-5.6-sol (cli:codex, job #343), com leitura direta do repositório
**Revisão:** Claude Fable 5 (parecer de revisão no Apêndice A)
**Projeto:** RF Kojiro / evolução de `jpsa13/RF-editor`
**Data:** 20/07/2026
**Estimativas:** pessoa-dias de um desenvolvedor sênior, incluindo testes técnicos; não incluem produção de conteúdo, licenciamento de assets ou pesquisa reversa prolongada de formatos proprietários.

## 1. Objetivo e não-objetivos

### 1.1 Objetivo

Evoluir o RF Loot Editor para o **RF Data Studio**, uma plataforma composta por:

1. **Admin Editor:** edição de fontes Excel, módulos visuais e, em fases posteriores, mapas, quests e edição assistida por IA.
2. **Data Core:** normalização das fontes, identidade estável, resolução de relações, validação, busca e exportação de snapshots públicos.
3. **Public Knowledge Base:** site público alimentado exclusivamente por snapshots versionados.
4. **Asset Pipeline:** transformação e publicação de ícones, imagens de monstros, mapas e minimapas calibrados.

O primeiro release público deve oferecer entidades pesquisáveis e as quatro relações de maior valor: monstro → drop; box → recompensa; recipe → insumo/resultado; shop → oferta.

A identidade pública obrigatória é:

```text
realm + entity_type + code
```

`items.id` permanece, no máximo, como chave técnica interna do banco local e nunca pode aparecer em URL, snapshot ou referência pública.

### 1.2 Não-objetivos

Não fazem parte do primeiro release: ligar o editor diretamente ao site; disponibilizar o SQLite do editor ao site; introduzir Neo4j, GraphQL, Redis, microserviços ou event bus; reescrever integralmente o editor; substituir Excel como formato autoritativo de edição; implementar map editor, quest editor ou minimap calibration antes do site; permitir que IA grave alterações autonomamente; publicar fontes desconhecidas usando inferência silenciosa de colunas; garantir compatibilidade de arquivos cujo layout não esteja declarado no entity registry.

## 2. Estado atual

O repositório é uma aplicação React 19 + Vite + Electron + SQLite/XLSX, com apenas scripts de desenvolvimento e build web em `package.json:6-14`, sem Forge ou outro empacotador em `package.json:22-38`; o processo principal mantém perfis, bancos e backups dentro de `electron/` em `electron/main.cjs:40-43` e `electron/main.cjs:376-394`, enquanto a janela sempre abre `localhost:5173` em `electron/main.cjs:437-460`. A UI está concentrada em uma única função `App`, iniciada em `src/App.tsx:215`, que acumula estado de perfis, grid, Box Builder, recipes, filtros e edição em `src/App.tsx:219-329`; embora a paginação aceite no máximo 1000 registros em `src/App.tsx:121`, a virtualização sem ícones só ativa acima de 1200 em `src/App.tsx:577-600`. O banco importa até 160 colunas genéricas em `extra_01…extra_160` (`electron/services/database.cjs:208-211`), cria o schema por chamadas ad hoc sem `PRAGMA user_version` (`electron/services/database.cjs:276-413`) e apaga/reinsere uma fonte em cada reimportação (`electron/services/database.cjs:827-856`), tornando `items.id` instável. Em `listItems`, o `LEFT JOIN boss_monsters` posterior ao agrupamento de mapas multiplica `COUNT` e linhas quando um monstro ocorre em mais de uma fonte (`electron/services/database.cjs:1204-1227` e `1288-1310`). A restauração aceita `backupName` diretamente em `path.join`, permitindo saída do diretório esperado (`electron/main.cjs:79-85`).

## 3. Arquitetura proposta

```text
RF Data Studio
├── Admin Editor
│   ├── Excel Grid
│   ├── Box Builder
│   ├── Loot Templates
│   ├── Recipes / Combines
│   ├── Map Editor                 [F4]
│   ├── Quest Editor               [F4]
│   └── Prompt-based Editing       [F5]
├── Data Core
│   ├── Entity Registry
│   ├── Import / Canonicalization
│   ├── Relationship Resolvers
│   ├── Validation
│   ├── Search Index
│   └── Snapshot Exporter
├── Public Knowledge Base
└── Asset Pipeline
```

### 3.1 Admin Editor

**Responsabilidade:** apresentar e editar fontes do perfil ativo; manter paginação, filtros, colunas e preferências existentes; produzir comandos de alteração estruturados; mostrar diagnósticos do Data Core; solicitar preview e confirmação antes de qualquer escrita; nunca acessar SQLite, filesystem, XLSX ou provedor de IA diretamente.

O fluxo existente deve ser preservado:

```text
React → window.electronAPI → preload → IPC → main → Data Core / serviços
```

O isolamento já está corretamente configurado com `contextIsolation: true` e `nodeIntegration: false` em `electron/main.cjs:445-449`.

**Código existente reaproveitado:** carregamento paginado (`src/App.tsx:2418-2453`); grid e edição de células (`src/App.tsx:5267-5640`); Box Builder (lógica `src/App.tsx:1554-1971`, UI `4709-4864`); templates de loot (`src/App.tsx:3413-3540`); visualização de combines (`src/App.tsx:4479-4703`); ponte IPC (`electron/preload.cjs:3-129`).

**Módulos novos:**

```text
src/
├── app/AppShell.tsx
├── features/
│   ├── grid/            (ExcelGrid.tsx, useItemsPage.ts)
│   ├── boxes/           (BoxBuilder.tsx)
│   ├── loot-templates/  (LootTemplatePanel.tsx)
│   ├── recipes/         (RecipeBrowser.tsx)
│   ├── validation/      (ValidationPanel.tsx)
│   ├── maps/            [F4]
│   ├── quests/          [F4]
│   └── prompt-editing/  [F5]
└── App.tsx              (composição temporária até AppShell assumir)
```

A extração será por fatias, preservando comportamento e chaves de `localStorage`; não haverá reescrita simultânea de `App.tsx`.

**Contrato com o Data Core:**

```ts
type PublicEntityKey = {
  realm: string;
  entityType: "item" | "monster" | "map" | "npc" | "recipe" | "shop" | "box";
  code: string;
};

type ChangeOperation =
  | { op: "setField"; target: PublicEntityKey; field: string; value: unknown }
  | { op: "upsertRelation"; relation: CanonicalRelationship }
  | { op: "deleteRelation"; relationKey: string };

type ChangeSet = {
  realm: string;
  source: "manual" | "template" | "prompt";
  operations: ChangeOperation[];
};

type ChangePreview = {
  changeSet: ChangeSet;
  affectedSources: string[];
  affectedRows: number[];
  before: unknown[];
  after: unknown[];
  validation: ValidationReport;
};
```

IPC mínimo novo: `core:list-entities`, `core:get-entity`, `core:validate`, `core:preview-change-set`, `core:commit-change-set`, `core:export-snapshot`. `commit-change-set` deve recusar operações sem preview válido correspondente ou com erros de validação.

### 3.2 Data Core

**Responsabilidade:** declarar o significado de cada fonte; transformar linhas genéricas `extra_N` em entidades e relações semânticas; manter identidade pública estável; detectar duplicados, referências quebradas e valores inválidos; resolver relações entre items, monstros, boxes, recipes e shops; gerar índice de busca; produzir snapshot imutável e verificável. A camada não escreve diretamente no site e não depende de React ou Next.js.

**Código existente reaproveitado:** leitura XLSX e construção das linhas brutas (`electron/main.cjs:1451-1604`); aliases de cabeçalho (`1732-1784`); limites de importação por fonte (`1802-1825`); persistência de labels/ordinais (`2043-2124`); transações SQLite (`database.cjs:925-954`); paginação e filtros SQL (`database.cjs:1025-1109`, `1182-1311`).

**Módulos novos:**

```text
electron/
├── data-core/
│   ├── registry/
│   │   ├── source-definition.schema.json
│   │   ├── drops.json
│   │   ├── boxes.json
│   │   ├── recipes.json
│   │   └── shops.json
│   ├── canonicalize.cjs
│   ├── resolve-relationships.cjs
│   ├── validate.cjs
│   ├── search-index.cjs
│   ├── snapshot-exporter.cjs
│   └── store.cjs
├── services/
│   ├── database.cjs        (fachada compatível durante migração)
│   └── migrations.cjs
└── ipc/core-handlers.cjs
```

Não será criado um repository por entidade. `store.cjs` concentrará as operações canônicas necessárias.

**Contratos:** `ImportedSource + SourceDefinition + Realm → CanonicalizationResult { entities, relationships, unresolvedReferences, diagnostics }`. Somente um `CanonicalizationResult` validado pode ser exportado. Fontes sem definição no registry continuam disponíveis no Excel Grid, mas recebem estado `raw_only` e não entram no snapshot.

### 3.3 Public Knowledge Base

**Responsabilidade:** páginas públicas de item, monstro, mapa, NPC, recipe, shop e box; navegação pelas relações resolvidas; busca por código, nome e aliases; exibição de versão e data do dataset; continuar servindo a última versão válida caso uma exportação falhe.

```text
site/
├── app/
│   ├── [realm]/
│   │   ├── item/[code]/page.tsx
│   │   ├── monster/[code]/page.tsx
│   │   ├── map/[code]/page.tsx
│   │   ├── npc/[code]/page.tsx
│   │   ├── recipe/[code]/page.tsx
│   │   ├── shop/[code]/page.tsx
│   │   └── box/[code]/page.tsx
│   └── search/page.tsx
├── components/
├── lib/snapshot.ts
└── package.json
```

Aplicativo Next.js separado dentro do mesmo repositório. Não importa módulos Electron e não abre o SQLite.

**Contrato com o Data Core — o único contrato é o snapshot publicado:**

```text
current.json → manifest.json → entities/*.ndjson → relationships/*.ndjson → search.json → assets-manifest.json
```

Publicação: (1) exportar para diretório temporário; (2) validar schema, contagens e SHA-256; (3) promover para diretório imutável da versão; (4) enviar todos os arquivos; (5) verificar os enviados; (6) atualizar `current.json` por último. O ponteiro só muda depois que a versão inteira estiver disponível.

### 3.4 Asset Pipeline

**Responsabilidade:** converter assets originais em formatos web; gerar nomes determinísticos e hashes; relacionar assets às chaves públicas; publicar `assets-manifest.json`; manter calibração separada da imagem original.

**Código existente reaproveitado:** DDS → PNG com `texconv` (`electron/main.cjs:1308-1327`); leitura de dimensões DDS (`954-988`); assets em `public/rf-icons/`; ferramentas `tools/crop-rf-race-symbols.ps1` e `tools/preview-race-icons.ps1`.

```text
tools/assets/
├── convert-item-icons.cjs
├── import-monster-images.cjs   [F4]
├── convert-map-spr.cjs         [F4]
└── calibrate-minimap.cjs       [F4]

assets/
├── source/        (não publicado automaticamente)
├── generated/
└── calibrations/

site/public/data/assets/<asset-version>/
```

O Data Core armazena `assetKey`, nunca caminho absoluto de máquina. Exemplo de entrada do manifest:

```json
{ "item:iyabc01": { "path": "items/iyabc01.a9b42c.png", "sha256": "a9b42c...", "width": 64, "height": 64 } }
```

## 4. Modelo de dados do Data Core

### 4.1 Camada bruta

A tabela `items` atual permanece temporariamente como staging e compatibilidade do grid. Suas colunas `extra_01…extra_160` não são contrato público. A fonte é vinculada a: `realm`, `source_key`, `source_type`, `registry_version`, `header_fingerprint`, `content_hash`.

### 4.2 Tabelas canônicas

| Tabela | Chave | Conteúdo |
|---|---|---|
| `core_sources` | `(realm, source_key)` | tipo da fonte, arquivo/aba, hashes, registry usado e importação |
| `entities` | `(realm, entity_type, code)` | nome, aliases e `attributes_json` |
| `entity_sources` | `(realm, entity_type, code, source_key, source_row)` | proveniência de cada entidade |
| `relationships` | `relationship_id` interno | relação tipada, origem/destino públicos, quantidade, chance, preço e proveniência |
| `validation_runs` | `run_id` | versão validada, datas e contagens |
| `validation_issues` | `issue_id` | regra, severidade, entidade, fonte, linha, coluna e mensagem |
| `search_documents` | chave pública | documento normalizado para FTS5/exportação |
| `snapshot_exports` | `dataset_version` | manifest, hash, validação utilizada e status de publicação |

Campos mínimos de `relationships`: `realm`; `relation_type` (drop | box_reward | recipe_input | recipe_output | shop_offer); `from_entity_type`; `from_code`; `to_entity_type`; `to_code`; `slot`; `quantity_min`; `quantity_max`; `chance_bp` (0..10000); `price`; `currency_code`; `resolution_status` (resolved | missing_source | missing_target | ambiguous); `attributes_json`; `source_key`; `source_row`.

Relações quebradas são preservadas para diagnóstico; o import não deve depender apenas de foreign keys que impeçam sua gravação.

Índices obrigatórios: `entities(realm, entity_type, code) UNIQUE`; `entities(realm, entity_type, display_name)`; `relationships(realm, relation_type, from_entity_type, from_code)`; `relationships(realm, relation_type, to_entity_type, to_code)`; `validation_issues(run_id, severity)`.

### 4.3 Entity Registry

Declarativo, versionado e validado por JSON Schema. Exemplo (layout do BoxItemOut, correspondente a `electron/main.cjs:1152-1162` e às chances em extra4/7/10/13 validadas em `src/App.tsx:560-575`):

```json
{
  "id": "box-item-out-v1",
  "registryVersion": 1,
  "match": { "filePattern": "^BoxItem.*\\.xlsx$", "sheet": "BoxItemOut", "requiredHeaders": ["Code"] },
  "sourceType": "box_rewards",
  "entity": { "entityType": "box", "code": { "column": "code", "coerce": "code", "required": true } },
  "repeatingRelations": [
    {
      "relationType": "box_reward",
      "targetEntityType": "item",
      "startColumn": 2, "stride": 3, "endColumn": 184,
      "fields": {
        "toCode":   { "offset": 0, "coerce": "code" },
        "quantity": { "offset": 1, "coerce": "integer", "min": 0 },
        "chanceBp": { "offset": 2, "coerce": "integer", "min": 0, "max": 10000 }
      }
    }
  ],
  "rules": [ { "id": "box-chance-total", "type": "sum", "field": "chanceBp", "equals": 10000 } ]
}
```

Valores permitidos inicialmente para `sourceType`: `entity_catalog`, `drops`, `box_rewards`, `recipes`, `shops`. F4 acrescenta: `maps`, `quests`, `npc_placements`.

Regras do registry: `sourceType` é obrigatório (não deduzido apenas pelo nome do arquivo); cada campo semântico aponta para uma coluna `extra_N`, coluna padrão ou grupo repetido; o fingerprint dos headers deve coincidir antes da canonicalização; alterar o significado de uma coluna exige nova `registryVersion`; `identityFields` devem ser declarados para linhas repetíveis; fontes desconhecidas ou incompatíveis ficam `raw_only`; o registry não pode mapear duas entidades diferentes para a mesma chave pública sem regra explícita de precedência.

### 4.4 Identidade

Entidade pública: `{realm}:{entity_type}:{code}` (ex.: `kojiro:item:iyabc01`, `kojiro:monster:00042`, `kojiro:recipe:combine-123`). Case-normalized para comparação, preservando o código original para exibição.

Para a tabela staging, F0 adiciona unicidade em `(source_file, excel_row)` e substitui delete/reinsert por update-or-insert. Isso preserva `items.id` quando a mesma linha é reimportada, mas não transforma esse ID em identidade pública.

### 4.5 Snapshot e manifest

```text
snapshots/<realm>/
├── current.json
└── <dataset-version>/
    ├── manifest.json
    ├── entities/{items,monsters,maps,npcs,recipes,shops,boxes}.ndjson
    ├── relationships/{drops,boxes,recipes,shops}.ndjson
    ├── search.json
    └── assets-manifest.json
```

`dataset-version` = `YYYYMMDDTHHMMSSZ-<12 primeiros caracteres do hash do conteúdo>`.

Manifest mínimo:

```json
{
  "manifestVersion": 1,
  "datasetVersion": "20260720T180000Z-a13f09cd8821",
  "realm": "kojiro",
  "registryVersion": 1,
  "createdAt": "2026-07-20T18:00:00Z",
  "validation": { "runId": "validation-id", "errors": 0, "warnings": 12 },
  "counts": { "entities": 0, "relationships": 0 },
  "sources": [ { "sourceKey": "BoxItem.xlsx::BoxItemOut", "sourceType": "box_rewards", "sha256": "..." } ],
  "files": [ { "path": "entities/items.ndjson", "sha256": "...", "bytes": 0, "records": 0 } ]
}
```

Cada registro de entidade contém chave pública, atributos e proveniência; cada relação usa chaves públicas completas. IDs SQLite não são exportados. `current.json` contém apenas a versão ativa e o hash do manifest.

## 5. Fases de implementação

### F0 — Correções críticas (4–6 pessoa-dias)

Entregas: (1) remover o `LEFT JOIN boss_monsters` redundante de `listItems` — alterar `itemBossExpression` para usar a existência em `boss_maps`, corrigir COUNT e consulta paginada, verificar as consultas irmãs de valores de filtro; (2) bloquear path traversal em restore — aceitar somente nomes simples retornados por `listBackupsForSource`, rejeitar caminho absoluto, `..`, `/`, `\` e resolução fora do diretório; (3) tornar a virtualização alcançável — ativar acima de 250 linhas, com ou sem ícones, preservando paginação SQLite; (4) preservar IDs internos em reimportações — índice único em `(source_file, excel_row)`, update-or-insert, remoção de linhas ausentes e reconstrução de effects na mesma transação.

Critérios de aceite: fixture com um monstro em três mapas retorna cada drop uma vez; `total` coincide com `COUNT(DISTINCT items.id)`; restore com `../arquivo`, caminho absoluto ou separador retorna erro sem alterar arquivos; restore legítimo funciona; página de 1000 linhas sem ícones renderiza somente a janela virtual; reimportar duas vezes o mesmo arquivo preserva os mesmos `items.id`; `npm run build` e `npm run lint` passam.

### F1 — Aplicação distribuível e banco migrável (5–8 pessoa-dias)

Entregas: Electron Forge com instalador Windows e artefato versionado; `loadURL` só em dev e `loadFile(dist/index.html)` em produção; perfis/backups/metadata/bancos sob `app.getPath("userData")`; migração única e recuperável dos dados legados de `electron/profiles` e `electron/backups`; migrations sequenciais com `PRAGMA user_version`; banco aberto só após `app.whenReady()` e resolução do perfil; scripts `start`/`package`/`make`; empacotamento de assets e rebuild do `sqlite3`.

Critérios de aceite: `npm run make` gera instalador utilizável; instalação em máquina limpa abre sem Vite; DevTools sem tentativa de conexão a localhost no build; dados persistem entre versões; perfis isolados; migração legado→userData preserva contagens com backup prévio; migration interrompida faz rollback; `PRAGMA user_version` correto.

### F2 — Contratos e extração segura da UI (8–12 pessoa-dias)

Entregas: testes com `node:test` (sem novo framework); constantes compartilhadas dos canais IPC; testes de contrato de payload/resposta; fixtures pequenas de ItemLooting, BoxItemOut e Combine; extração incremental de Excel Grid, Box Builder, Loot Templates e Recipes; `App.tsx` reduzido a composição/navegação; serviço único de paginação no renderer.

Critérios de aceite: teste falha se preload invocar canal não registrado; import → list → edit → reimport funciona em fixture; teste confirma que somente aba/células pretendidas são alteradas; chaves de `localStorage` continuam válidas; filtros/ordenação/paginação/resize mantêm comportamento; Box Builder conserva total 10000; nenhuma feature extraída usa Node/Electron direto; build, lint e test passam.

### F3 — Data Core, snapshot e site público (18–28 pessoa-dias)

Entregas: entity registry v1 para drops, boxes, recipes e shops; schema canônico e migrations; canonicalização e resolvers; validações (chave duplicada, header incompatível, referência inexistente/ambígua, chance fora de 0..10000, soma de box ≠ 10000, recipe sem insumo/resultado, shop offer inválida); índice FTS5; exporter NDJSON + manifest + SHA-256; publicação imutável com troca atômica de `current.json`; site Next.js com todas as páginas de entidade; busca por código/nome/alias; item icons publicados pelo Asset Pipeline.

Critérios de aceite: as 4 relações consultáveis nos dois sentidos; toda entidade exportada com `realm/entityType/code`; nenhum `items.id` público; exportação com erro de validação bloqueada; exportações do mesmo conteúdo → hashes equivalentes; falha antes da troca do ponteiro mantém versão anterior; manifest rejeita arquivo adulterado; site sobe apenas com pasta de snapshot + assets; busca encontra código exato, nome e alias; desligar o editor não derruba o site.

### F4 — Mapas, quests e expansão de assets (20–35 pessoa-dias, após amostras autoritativas)

Entregas: registry para mapas, NPC placements e quests; conversor SPR→PNG; imagens de monstros; map editor; quest editor; calibração de minimap (armazenando `realm`, `map_code`, dimensões, `control_points`, `affine_transform`, `rms_error`, `calibration_version`); relações monstro/NPC/quest → mapa; inclusão no snapshot.

Critérios de aceite: golden files e fingerprint por formato; conversão determinística; editores escrevem só no arquivo/aba/células selecionados com backup; ≥3 pontos de controle reproduzem coordenadas dentro da tolerância; RMS exibido e calibrações acima do limite não publicam; páginas de mapa mostram entidades relacionadas; assets com hash/dimensões/proveniência.

### F5 — Prompt-based Editing (10–16 pessoa-dias)

Fluxo obrigatório: dataset validado → usuário seleciona escopo e escreve instrução → IA propõe `ChangeSet` → Data Core valida → preview linha a linha → confirmação humana → gravação em transação → revalidação.

Entregas: seleção explícita de realm/fonte/escopo; `ChangeSet` estruturado; validação determinística; preview; commit pelo mesmo caminho da edição manual; log de auditoria sem prompt sensível ou credencial; limite de operações/timeout/cancelamento; provedor e modelo configuráveis no processo principal.

Critérios de aceite: desabilitada se a validação-base tiver erros; renderer nunca recebe credencial; IA sem ferramenta de escrita direta; resposta fora do schema rejeitada; referência inexistente/chance inválida/fora do escopo bloqueia preview; fechar preview não altera nada; commit gera backup + grava + reimporta + revalida; teste com provedor falso comprova zero escrita antes da confirmação; edição manual funciona sem rede/IA.

## 6. Decisões e alternativas rejeitadas

| Decisão | Alternativa rejeitada | Justificativa |
|---|---|---|
| Snapshot como fronteira pública | Site lendo SQLite/editor | desacopla disponibilidade, segurança e deploy |
| `realm + entity_type + code` | `items.id` | ID técnico e sensível a reimportação |
| Registry declarativo versionado | Regexes espalhadas pelo código | significado de `extra_N` auditável |
| SQLite relacional | Neo4j | 4 relações iniciais não justificam outro banco |
| Sem API pública no 1º release | GraphQL/REST | o site precisa apenas do snapshot |
| Índice local/estático | Redis | sem requisito de escala |
| Next.js consumindo snapshot | Compartilhar módulos Electron | evita acoplamento a CJS/filesystem/IPC |
| Extração incremental de `App.tsx` | Reescrita completa | reduz regressão |
| `node:test` | framework adicional | cobre contratos CJS sem nova dependência |
| ChangeSet validado | texto livre executado pela IA | edição determinística e revisável |
| Um único repositório | multi-repo imediato | versionamento conjunto do contrato |
| JSON/NDJSON versionado | banco público replicado | verificável, cacheável, reversível |

## 7. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Layouts Excel variam entre releases | fingerprint de headers, registry versionado, estado `raw_only` |
| Mapeamento semântico incorreto de `extra_N` | fixtures autoritativas e aprovação por fonte antes da publicação |
| Códigos duplicados no mesmo realm/tipo | validação bloqueante e regra explícita de alias/precedência |
| Perda de dados na escrita XLSX | backup, escrita célula-a-célula, golden files, reimportação pós-write |
| Migração de perfil corromper isolamento | inventário, backup, cópia verificada, marcador de migração |
| Snapshot parcialmente publicado | versões imutáveis e ponteiro atualizado por último |
| Site preso a detalhes do editor | contrato de snapshot independente de IPC e SQLite |
| Índice de busca crescer demais | `search.json` inicial; particionar acima de 5 MB comprimidos |
| Assets sem direito de publicação | inventário de origem/licença e bloqueio de não aprovados |
| Variantes desconhecidas de SPR/coordenadas | fixtures por versão e calibration versionada |
| IA inventar códigos/relações | schema fechado, resolução pelo Data Core, validação antes do preview |
| Custo/indisponibilidade do provedor de IA | feature opcional; fluxo manual completo |
| Segredo exposto no renderer/log | credencial só no main + redaction obrigatória |
| Refatoração de `App.tsx` causar regressões | extração por feature, contratos, build a cada fatia |

## 8. Perguntas abertas para o owner

1. Um perfil atual corresponde exatamente a um `realm`, ou um perfil poderá conter mais de um realm?
2. Qual slug público representa o servidor inicial: `kojiro` ou outro?
3. Quais são os arquivos, abas e versões autoritativas para drops, recipes e shops? (`BoxItemOut` já tem layout parcialmente confirmado pelo código.)
4. Quando o mesmo código aparece em fontes conflitantes, qual fonte tem precedência?
5. Warnings permitem publicação? Proposta: erros bloqueiam; warnings ficam no manifest e exigem confirmação do operador.
6. Onde o site e os snapshots serão hospedados? (Define a implementação da troca atômica de `current.json`.)
7. Quais idiomas no primeiro site e qual fonte contém os nomes traduzidos?
8. Há autorização para publicar ícones, imagens de monstros, mapas e minimapas derivados dos arquivos do jogo?
9. Quais amostras autoritativas de SPR, mapas, quests e coordenadas estarão disponíveis para F4?
10. Em F5, qual provedor/modelo, orçamento por operação, retenção e telemetria são aceitáveis?
11. O histórico de ChangeSets identifica só o perfil local ou também um usuário autenticado?
12. A aprovação cobre iniciar F0 imediatamente, deixando hospedagem, assets e IA como gates de F3–F5?

---

## Apêndice A — Revisão da spec (Claude Fable 5)

**Veredito: APROVAR com 3 ajustes menores.** A spec respeita todas as decisões do parecer (snapshot como única fronteira, identidade pública sem `items.id`, prompt-editing atrás da validação, map/quest em F4+, sem Neo4j/GraphQL/Redis) e as referências de arquivo:linha foram conferidas por amostragem contra o repositório (`PAGE_SIZE_OPTIONS` em App.tsx:121, `extraItemColumns` em database.cjs:208, `loadURL` em main.cjs:460 — corretas).

**Ajustes aplicados/recomendados:**

1. **Registry do BoxItemOut** — no exemplo original do autor, o código da box apontava para `extra_01`; na staging atual o código da linha vive na coluna fixa `code` (o `upsert-boxitemout-box` escreve o código na primeira célula da linha, que o import mapeia para `code`). O exemplo acima já está corrigido para `"column": "code"`. Validar contra uma fixture real na F3 antes de congelar o schema do registry.
2. **F0 item 4 (update-or-insert por `(source_file, excel_row)`)** é uma adição do autor além do parecer — correta e desejável, mas atenção ao caso de linhas deletadas na planilha que deslocam `excel_row` das seguintes: nesse cenário o "mesmo id" muda de conteúdo. Aceitável porque a identidade pública nunca é `items.id`; documentar o comportamento no teste de aceite.
3. **Estimativas** — os totais (F0–F3: ~35 a 54 pessoa-dias) são consistentes com o intervalo de 6–10 semanas do parecer para chegar ao site. F4 (20–35 dias) confirma a decisão de mantê-lo fora do caminho crítico.

**Ponto forte da spec:** os critérios de aceite são objetivos e testáveis fase a fase — é o que faltava ao projeto (que nunca teve testes). A resposta à pergunta 12 pode destravar F0 imediatamente sem esperar as decisões de hospedagem/assets/IA.
