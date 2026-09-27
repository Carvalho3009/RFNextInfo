# Validação v40 — publicação

- Suíte final no ZIP extraído: 302 testes executados, 295 aprovados e 7 ignorados por fixtures externas.
- Testes específicos de mundo, fila e interface: 7 aprovados.
- Compatibilidade do receptor: 4 testes aprovados, incluindo eventos antigos, quatro tipos novos, metadados inválidos e lotes realmente gerados pelo serializador/fila do cliente.
- Mundo divergente ou login rejeitado não inicia conexão com o serviço do jogo. Mundo desconhecido mantém nome nulo.
- Reenvio após trocar configuração mantém a identificação original; eventos antigos não são reatribuídos.
- Nenhum acesso ao jogo, compra ou upload ao site foi feito para esses testes.
- Receptor compatível publicado sobre a imagem real, preservando eventos v2. 80 verificações passaram no contêiner ativo; health local e público HTTP 200. PostgreSQL não foi reiniciado.
- Revisão final do agent-organizer aprovada; `git apply --check` do patch passou contra o checkout atual do site.

Receptor compatível publicado; distribuição da v40 autorizada por Carlos. Eventos enviados com `game_server` são aceitos e preservados, sem alterar filtros ou projeções por mundo.
