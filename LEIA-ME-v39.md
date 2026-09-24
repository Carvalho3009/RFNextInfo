# RF NEXT Companion v39

Correção do erro `AttributeError: 'str' object has no attribute 'configure'` ao dimensionar a janela. O callback do nome da conta agora mantém a referência ao widget correto; a reutilização da variável `label` durante a construção da tela não o altera.

Feche o programa e extraia este ZIP sobre a pasta da v38. O pacote não contém os diretórios de contas, bancos de envio, lista de compras nem preferências locais. Mantenha esses arquivos existentes. Execute `run-client.bat`.

As funcionalidades e limitações da v38 permanecem descritas em `LEIA-ME-v38.md` e `INVENTARIO-DASHBOARD-v38.md`. Esta correção não altera autenticação, heartbeat, consultas ou compras.
