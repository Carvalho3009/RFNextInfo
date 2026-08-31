# Contrato Colecao/Codex entre Agent e site

O evento continua sendo `progress.collection_snapshot`. Os campos existentes
permanecem obrigatorios conforme o receptor atual. Esta extensao adiciona apenas
campos opcionais derivados de dados ja confirmados pelo decoder e pelo catalogo:

- `collection_type` no payload;
- `completed_slot_indexes` em cada registro catalogado;
- `missing_slot_indexes` em cada registro catalogado.

Os indices sao base zero, ordenados, unicos e limitados aos dez slots suportados
pelo decoder/catalogo atual. Quando o catalogo nao conhece a colecao, o Agent
mantem o fallback anterior (`completed_slots`, `total_slots` e `completed`) e nao
emite as listas de indices.

O payload nao inclui UID de instancia de item, valor bruto de slot, pacote,
opcode ou outra evidencia interna. O isolamento continua sendo por instalacao,
cliente, sessao opaca e personagem confirmado.

## Ordem obrigatoria de implantacao

1. Publicar primeiro o receptor que aceite tanto o payload antigo quanto os
   campos opcionais novos.
2. Validar a ingestao dos dois formatos no site.
3. Somente depois publicar o Agent que emite a extensao.

Nao ha negociacao de capacidades nesta etapa. Um receptor antigo pode rejeitar
os campos novos; por isso a ordem acima e um requisito de compatibilidade.

Categorias de inventario nao fazem parte desta extensao. O site deve deriva-las
pela referencia canonica usando `item_index`, ja presente em
`inventory.snapshot`, sem duplicar classificacao no protocolo do Agent.
