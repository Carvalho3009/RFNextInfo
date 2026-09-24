# Validação v36

- Cliente: `python -m unittest discover -s tests -q`: 242 testes, 235 aprovados e 7 ignorados por ausência de capturas de regressão. Após a guarda final contra iniciar outra compra antes de processar o resultado anterior: 46 testes dirigidos aprovados, incluindo um teste novo.
- Interface: navegação e callbacks independentes com widgets simulados; projeções Local/Global, IDs exatos, filtro de refino, estados parciais, sincronização sem login do jogo, preparo sem envio, invalidação e revalidação após confirmação modal.
- Compras preparadas: lotes inteiros, mercado explícito, IDs de 64 bits, nenhuma alocação duplicada, bloqueio de ofertas conflitantes/expiradas e validação do contrato.
- Saldo reservado por item da lista: compra confirmada seguida de nova captura/lista não prepara unidade adicional; resultado incerto mantém reserva, bloqueio/rejeição libera quantidade. Guarda impede segunda compra enquanto o resultado anterior aguarda processamento pela interface.
- Site: três testes específicos aprovados; regressão characters/sync aprovada pelo especialista.
- Integração local: shopping.fetch real → assinatura Ed25519 real → FastAPI → SQLite → shopping.validate. Isolamento de conta, nonce repetido, assinatura inválida e revogação verificados. Transporte externo e execução de compras bloqueados no teste.
- Nenhuma alteração no protocolo, transporte, workers de consulta ou manutenção de heartbeat nesta versão.
- Sem inspeção gráfica automatizada, compra real ou publicação do endpoint no servidor. PostgreSQL real não exercitado neste teste local.

Commit do backend local: 4fef20a. A aplicação do patch ao servidor e publicação exigem a etapa de deploy; cliente isolado não torna a rota pública disponível.
