# RF Next — v31

## Conferência dos requisitos

- [x] Mercado contínuo: botão, repetição, intervalo, parada e worker próprios; consulta local e global, sem ranking ou heartbeat automático.
- [x] Ranking contínuo: controles e worker próprios; EXP e três facções; requer heartbeat iniciado separadamente, sem acionar mercado.
- [x] Consulta completa: inicia/reutiliza o heartbeat, espera três confirmações recebidas, consulta rankings, mercado local/global e envia os resultados.
- [x] Heartbeat independente: permanece ativo ao terminar/parar consultas. Só “Parar heartbeat”, “Parar tudo” ou fechar o programa encerram esse worker. Falhas de rede continuam possíveis e aparecem no estado próprio.
- [x] Timer visível por modo: começa depois da consulta e da tentativa de envio. Erros do ciclo não desativam a repetição. Cancelar interrompe a espera.
- [x] Até 300 personagens por ranking no decoder e envio; EXP já solicita 300. O pedido conhecido das facções não possui campo de quantidade: conserva até 300 se o servidor devolver; uma resposta com 100 continua com 100.
- [x] pc_id enviado nas ofertas; vínculo de vendedores fica no site. character_uid e nome conservados nos rankings.
- [x] Recuperação de consulta de mercado remove o erro transitório do resumo quando a repetição tem sucesso.
- [x] Reenvio HTTP: conexão nova, mesmo lote/chave de idempotência, nova assinatura/nonce; recebidos não voltam à fila. Fila serializada entre os workers para evitar concorrência na mesma instalação.
- [x] Servidor padrão: https://apirf.karvalho.dev.br.
- [x] Credenciais e payloads não são ocultados nos registros exportados. O log visual continua limitado; resultados por operação também são exportados.

## Uso

Extraia sobre a pasta do cliente, preservando config.json, session.json, a base de itens existente e companion-state (identidade e fila). Abra run-client.bat e confira “v31” no título.

Cada linha tem seu próprio “Continuamente”, intervalo e “Parar”. Para ranking individual, inicie primeiro o heartbeat. Mercado e ranking individuais podem rodar juntos. A consulta completa deve ser iniciada após encerrar as consultas individuais; usa o mesmo worker de heartbeat e o mantém ao terminar.

## Validação e limites

Testes de comportamento verificam os comandos dos botões, isolamento, repetição após falhas, espera real por três eventos de heartbeat, timer após envio, cancelamento, reconexão e quatro rankings sintéticos com 300 registros. Testes TCP locais utilizam servidor simulado; não provam coexistência das conexões no servidor do jogo.

A alteração de contrato do site para rankings acima de 100 foi preparada e validada em container isolado. Compatibilidade publicada no site e verificada apos a atualizacao. “Accepted” confirma recebimento; não confirma conclusão do processamento nem exibição no site.
