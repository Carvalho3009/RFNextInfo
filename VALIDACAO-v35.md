# Validação v35

- Suíte oficial: `python -m unittest discover -s tests -q`.
- 226 testes executados antes da revisão final: 219 aprovados e 7 ignorados por ausência de capturas. Após revisão de cancelamento e botões, 23 testes específicos aprovados, incluindo um teste adicional de encerramento do worker.
- Serializer preserva os 33 bytes observados; valida tipos e limites dos campos.
- Verificação recusada, flag diferente de 1, payload inválido e timeout não enviam compra.
- Sessão nova autentica antes da verificação; não consulta mercado/rank.
- Sessão persistente inicializa uma vez, compra no mesmo socket e mantém pulsos durante a espera e após o resultado. Nenhuma segunda conexão é criada.
- Botão de heartbeat chama a fila do worker, sem chamar autenticação ou upload.
- Cancelamento anterior ao envio e encerramento do worker resolvem pedidos pendentes sem reenvio.
- Sucesso, rejeição, resposta divergente/inválida e timeout de compra cobertos; um único 0x1D12 por pedido.

A descoberta na raiz incluiu cópias antigas não rastreadas de testes: 15 erros por configuração fora do diretório e uma expectativa antiga de integração. O comando oficial acima usa tests/, como nas versões anteriores.

Compra real e interação visual permanecem para teste manual. Nenhum pedido foi enviado ao servidor do jogo durante o desenvolvimento.
