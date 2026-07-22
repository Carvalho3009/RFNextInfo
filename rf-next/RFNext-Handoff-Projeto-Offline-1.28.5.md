# Handoff do Projeto — RF NEXT OFFLINE (1.28.5)

Projeto: `K:\MCP\projects\rf-next`

## Objetivo e escopo do projeto

Análise offline do cliente Android 1.28.5 (sem nova captura de tráfego e sem Ghidra runtime), usando:

- `K:\MCP\projects\rf-next\analysis\1.28.5\rfnext-data.sqlite`
- `K:\MCP\projects\rf-next\analysis\1.28.5\libUnreal.so`
- `K:\MCP\projects\rf-next\analysis\1.28.5\rfnext_frame_decode.py`

## Estado atual do projeto

- Entrega mais completa já processada: `K:\MCP\projects\rf-next\analysis\1.28.5\fable-run\RFNext-Queue-Resultado-2026-07-21.md`
- Handoff da rodada anterior (lote): `K:\MCP\projects\rf-next\analysis\1.28.5\RFNext-Handoff-Analise-OffLine-389.md`
- Fila de continuidade definida para próximos lotes: `K:\MCP\projects\rf-next\analysis\1.28.5\RFNext-Queue-Analises-OffLine-Para-fable.md`

## O que já está consolidado

- Mobs/EXP/loot com relação NPC→Reward: `K:\MCP\projects\rf-next\analysis\1.28.5\RFNext-Mobs-EXP-Loot-map.md`
- Análise estática ampla (classes/progressão/equips/eventos/economia): `K:\MCP\projects\rf-next\analysis\1.28.5\RFNext-Analise-Offline-Ampla-1.28.5.md`
- Capturas e logs úteis: `K:\MCP\projects\rf-next\captures\` e `K:\MCP\projects\rf-next\analysis\1.28.5\exports\`

## Entregas por frente (RFNEXT-1 a RFNEXT-6)

- RFNEXT-1: protocolo de rede não tratado — **médio/inferido** (mapa por opcode confirmado; layout de payload ainda pendente de validação com `read_elf_utf16.py` com permissão de Python/execução completa).
- RFNEXT-2: mobs/drop/loots — **alto** (cadeia RewardIndex/SubGroup/Item estruturada; action 1006 confirmado como finalizador com bônus de EXP 10x em amostra).
- RFNEXT-3: evolução/progressão/classes — **alto**.
- RFNEXT-4: eventos e conteúdo — **alto** (estrutura estática; estado ao vivo em manutenção dinâmico).
- RFNEXT-5: economia interna — **alto**.
- RFNEXT-6: estrutura técnica/decode — **alto**.

## Bloqueios conhecidos e próximos passos

- Falta de execução completa de `python`/`sqlite3` na passada anterior impediu extração final de bytes para RFNEXT-1.
- Para fechar 100% do projeto, priorizar:
  1. Rodar uma passada de RFNEXT-1 com `read_elf_utf16.py` e validação de payloads para opcodes 031b/031c, 031e/031f, 0330/0331, 0a01-0a16, 0c01-0c0a, 0c11-0c16, 1702, 1802/1803/1805/1806/1809/180a/1814, 2301/2302.
  2. Consolidar os achados em um documento único de entrega operacional.
  3. Manter operação fora de Ghidra e sem controle de tela, conforme decisão atual.

## Contexto para próximo agente

- O projeto alvo oficial e persistente já está em `K:\MCP\projects\rf-next` (evitar gravações permanentes fora desse padrão, salvo ordem explícita contrária).
- O último job disparado foi `389`; status final registrado como `done` com pendência técnica somente em RFNEXT-1.
