# Handoff — RF NEXT OFFLINE (libUnreal.so) — lote local-ai job 389

Data: 2026-07-22  
Projeto: `K:\MCP\projects\rf-next\analysis\1.28.5`  
Modelo/worker: `cli:claude` + `fable`  
Job: `389` (pattern `fanout`)

## Estado atual

- Status observado: `done`  
- Caminho de retorno sugerido: `K:\MCP\projects\rf-next\analysis\1.28.5\fable-run\RFNext-Queue-Resultado-2026-07-21.md`  
- Origem de dados principal:
  - `rfnext-data.sqlite`
  - `libUnreal.so`
  - `rfnext_frame_decode.py`

## Artefatos obrigatórios no caminho do projeto

- `RFNext-Queue-Analises-OffLine-Para-fable.md`
- `RFNext-Analise-Offline-Ampla-1.28.5.md`
- `RFNext-Mobs-EXP-Loot-map.md`
- `rfnext_frame_decode.py`

## Objetivo do próximo agente

Consolidar o resultado do lote em formato de entrega operacional:

- Por job (`RFNEXT-1` a `RFNEXT-6`), registrar:
  - confiança (`alta/média/baixa`),
  - achados com fonte (tabela/arquivo/campo),
  - suposições,
  - limitações,
  - próximos passos acionáveis.

## Pendências conhecidas

- `RFNEXT-1` ficou em "média": mapeamento de opcodes não tratados com inferência por string/opcodes, faltando validação por execução do parser (bytes reais de captura ou fluxo interno).
- `RFNEXT-6` depende de artefato de comparação da versão `1.27` para regressão completa; se ausente, registrar bloqueio e produzir plano de análise parcial com base apenas em 1.28.5.

## Entrega mínima solicitada

1. Preencher um resumo consolidado por job com os blocos:
   - "achado", "fonte", "nível de confiança", "como validar"
2. Atualizar o master report com novos blocos somente se os achados forem comprovados em arquivo/consulta.
3. Entregar plano curto de continuidade sem captura (offline-only), com ordem de execução:
   - `RFNEXT-2` → `RFNEXT-5` → `RFNEXT-1` (validação), `RFNEXT-6` (quando 1.27 disponível).

## Observações técnicas para continuidade

- Não usar Ghidra neste ciclo (impacto de desempenho já foi registrado).
- Priorizar consultas SQL no `rfnext-data.sqlite` e análise estática do binário.
- Registrar sempre quando o dado é inferido vs confirmado.
