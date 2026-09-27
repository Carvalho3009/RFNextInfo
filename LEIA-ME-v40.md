# RF NEXT Companion v40

Inclui o mundo confirmado pelo login nos resultados e nos eventos de mercado e ranking enviados ao Companion. O campo `game_server` contém `world_id` e `world_name`; o nome confirmado de 5024 é Menkar 4. Demais nomes permanecem nulos. Local/Global continua no campo existente `server_type`.

O contexto acompanha o documento salvo na fila; reenvios não usam o mundo da conta atualmente selecionada. Resultados antigos sem essa identificação continuam sem ela.

O receptor compatível foi publicado em 26/09/2026 em `https://apirf.karvalho.dev.br`. A atualização do cliente pode ser instalada; receptores antigos de outras instalações ainda rejeitam o novo campo.

A identificação recebida é preservada no evento. Esta versão não adiciona filtros por mundo nem altera as projeções do site.

Depois da atualização do receptor, feche o cliente e extraia o pacote sobre a instalação existente, preservando suas contas, configurações e bancos locais.
