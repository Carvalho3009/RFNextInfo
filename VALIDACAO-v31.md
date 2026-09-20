# Validação da v31

## Cliente

- Testes de execução: `tests/test_complete.py` verifica os três conjuntos de botões, repetição independente, parada, dois workers concorrentes, timer após o envio e ranking liberado apenas após o terceiro heartbeat.
- Heartbeat: a consulta completa usa o mesmo serviço da interface. Não existe mais condição especial para os testes ignorarem as confirmações. O encerramento da consulta não encerra o worker compartilhado.
- Mercado: `test_successful_retry_removes_only_recovered_error` reproduz queda, reautenticação e resposta válida. O resultado final fica completo e sem erro residual.
- Upload: `test_broken_pipe_reopens_connection_for_same_batch` confirma corpo e chave idempotente iguais, mas nonce novo, na segunda tentativa. Lotes já recebidos não são reenviados.
- Ranking: quatro payloads sintéticos com 300 personagens passam pelo mapeamento; posições anteriores até 300 são conservadas. Respostas reais de facção continuam limitadas ao que o jogo devolver.
- Regressão do pacote extraído: 211 testes, 204 aprovados e 7 ignorados (testes que dependem de capturas externas não fornecidas como fixtures).
- O ZIP é comparado byte a byte com todos os módulos e testes do diretório de origem pelo empacotador.

## Site: compatibilidade publicada

O contrato anterior exigia exatamente 100 personagens. O contrato publicado aceita de 1 a 300 com posicoes contiguas e sem duplicacao. A correção específica está em `site-compat-v31/contracts.patch`, derivada do arquivo do container em execução, sem incluir as outras mudanças locais do site.

O teste isolado aceita EXP e cada facção com 300 registros, conserva suporte a 100 e rejeita posições duplicadas e limite acima de 300. Compatibilidade publicada e verificada no container ativo; API publica /healthz HTTP 200.

Os recibos do upload confirmam recebimento, não exibição. A consulta ao banco confirmou que a fila de processamento estava avançando; a captura mais recente ainda não foi confirmada como visível. Esta versão do cliente não é uma correção desse processamento interno do site.

## Limites de evidência

Não houve login nem consulta contra o servidor real do jogo nesta validação. A coexistência real do heartbeat com conexões de mercado e ranking precisa do teste com a sessão do usuário. Nenhuma credencial da sessão foi incluída no pacote.
