# Validação v32

- Teste de protocolo simulado comprova 0x0201/0x0202 antes de 0x1A01, quatro rankings recebidos e ausência de pedidos de mercado nesse modo.
- Rejeição da inicialização impede envio de pedidos de ranking.
- Quatro timeouts produzem failed; EXP recebido e facções ausentes produzem incomplete.
- Consulta completa preserva falha dos rankings mesmo com mercado e upload bem-sucedidos.
- Estado de encerramento do worker é retido com horário para exportação.
- Regressão completa e validação do ZIP extraído executadas; resultados em .validation/v32-tests.log e .validation/v32-package-tests.log na origem.
- Sem teste de login real, sem alteração de credenciais e sem alteração no site nesta versão.
