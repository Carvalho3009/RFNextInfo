# Fila de próximas análises offline (sem captura)

Contexto: RF NEXT 1.28.5, versão já carregada em
`K:\MCP\projects\rf-next\analysis\1.28.5\rfnext-data.sqlite` e `libUnreal.so`.

Objetivo desta rodada: priorizar análise máxima sem tráfego e sem Ghidra.

## Instruções de envio para o `cli:claude fable`

Como envio recomendado, use este formato de mensagem:

```
taskset:
- ID: RFNEXT-1
  foco: protocol
  pasta: C:\Users\celc3\OneDrive\Documentos\RF NEXt
- ID: RFNEXT-2
  foco: mobs-drop
  pasta: C:\Users\celc3\OneDrive\Documentos\RF NEXt
...
```

Também pode enviar cada bloco abaixo como `prompt` individual.

## Jobs prontos (RFNEXT-1 a RFNEXT-6)

### RFNEXT-1
Foco: protocolo de rede (destrinchar classes FL2C/FC2L/FG2C não tratadas)

- Prioridade: alta
- Fonte local: `libUnreal.so`, `RFNext-Cleartext-dispatchers.md`, `read_elf_utf16.py`
- Entrega esperada: lista de structs por opcode + parser/descrição em dicionários.
- Entradas importantes:
  - 031b/031c (boss status/list)
  - 031e/031f (boss position)
  - 0330/0331 (random boss status/list)
  - 0a01..0a16 (quests)
  - 0c01..0c04 (fases/mapa)
  - 0c05..0c0a (world boss HP, contribuição, ranking)
  - 0c11..0c16 (guild raid / party dungeon)
  - 1702, 1802,1803,1805,1806,1809,180a,1814
  - 2301,2302
- Perguntas finais: mapear campos numéricos com tipos e semântica mínima por payload.

### RFNEXT-2
Foco: árvore de drop/reward de mobs (loot estático + gatilhos de finalizador)

- Prioridade: alta
- Fonte local: `rfnext-data.sqlite`
- Entrega esperada: por NPC (`RF_MobIndex`), top drops, chance, tipo (FieldDrop/Mode/First/Last hit), tabela de recompensas finais.
- Queries base para validar:
  - tabela/colunas de recompensa por mob
  - `RF_MonsterListTable` + `RF_DropGroupTable` + `RF_DropItemTable`
  - `RF_MobReward`/equivalentes usados na cadeia de NPC→dropgroup
- Incluir: “mobs com exp bonus por finalizador”, “drop com contador mínimo/máximo”, “itens que só caem em modo 1006”.

### RFNEXT-3
Foco: evolução de xp e progressão de classe (sem capture)

- Prioridade: média
- Fonte local: `rfnext-data.sqlite`
- Entrega esperada: matriz `classe x grade x atributo`, custo médio de evolução por etapa e validação de fórmulas já usadas.
- Cobrir:
  - limites de skill por classe
  - escala de buff/debuff por nível
  - gap de pontuação entre classes no mesmo rank de nível (1..200)

### RFNEXT-4
Foco: conteúdo e progressão de eventos (sem dados de vivo)

- Prioridade: média
- Fonte local: `rfnext-data.sqlite`, `RFNext-*protocol*`, `RFNext-*network*`
- Entrega esperada: cronologias e dependências de eventos/mundos por região.
- Entregar:
  - mapa de fases por evento (Arcane Trial, Rakan, Tri-Placas, guild raid)
  - escalas e requisitos por mapa/reino/nível
  - timers e pesos de spawn normal/stable/unstable

### RFNEXT-5
Foco: economia e economia interna (craft/dismantle/auction)

- Prioridade: média
- Fonte local: `rfnext-data.sqlite`, `RFNext-Market*`, `RFNext-Cleartext-dispatchers.md`
- Entrega esperada: cadeia de custo/retorno sem captura, com cenários.
- Entregar:
  - tabela de “valor esperado por item” para `prime`, `dismantle`, `alchemy`, `talic`
  - concentração de itens de alto impacto em recompensas e drops
  - impacto de `exchange` no fluxo de circulação (sem runtime)

### RFNEXT-6
Foco: mapa técnico/estabilidade de execução

- Prioridade: baixa/média
- Fonte local: `libUnreal.so`, `RFNext-Frame-decompressor.md`, `RFNext-Outer-frame-parser-*`
- Entrega esperada: pontos frágeis do parser (offset/versão), regressões prováveis de estrutura.
- Validar:
  - mudanças prováveis de `FRAME` entre 1.27 e 1.28
  - opcodes que mudam tamanho semântica mas mantêm nome
  - campos de tempo (timestamp, durações) não usados.

## Critério de aceite para cada job

- Lista explícita de suposições
- Estrutura de campos com unidade e tipo
- Exemplo mínimo de 5 payloads decodificados por caso
- Resultado final com confidence: alto/médio/baixo
- Se não tiver prova em dados, deixar em `status: inferido`
