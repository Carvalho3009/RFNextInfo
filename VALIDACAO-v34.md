# Validação v34

222 testes: 215 aprovados, 7 ignorados por ausência de capturas de regressão.
- Serializer reproduz exatamente os 33 bytes do pedido observado.
- Limites e tipos de todos os campos, incluindo rejeição de bool/negativos/overflow.
- Confirmação, rejeição, resposta divergente/inválida e timeout; somente um envio.
- Sessão autenticada termina após a compra sem solicitar mercado/ranking.
- Cancelar confirmação não inicia sessão; confirmar aciona worker de compra sem upload.
- Compra em servidor real e interação visual permanecem para o teste manual.
