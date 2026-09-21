# v33 — limpeza do banco de envios

Resultados e lotes já confirmados pelo Companion são removidos automaticamente ao enviar ou reenviar. Contagem acumulada, sequência e vínculo são preservados. Pendentes, rejeitados e resultados ainda não preparados permanecem intactos.

Use a mesma pasta companion-state. Clique em Reenviar pendentes para executar a manutenção do banco existente. Não apague o banco nem a identidade.

A compactação ocorre quando há pelo menos 1 MiB e 20% de espaço livre. Pendentes continuam ocupando espaço até confirmação do servidor.

Também inclui o diagnóstico detalhado de erros HTTP do Companion. Não altera a consulta de mercado, ranking ou heartbeat.
