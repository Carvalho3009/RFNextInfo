# Inventário do dashboard e importação — v38

Fontes verificadas nesta implementação:
- `../agent/core/rfnext_frame_decode.py`: decoder completo, layouts de setembro/2026.
- `../agent/core/biosuits.json`: catálogo versionado 1.28.5, copiado no pacote; IDs novos sem catálogo permanecem numéricos.
- `rfnext_market/auth.py` e `character.py`: contratos de autenticação e template de entrada existentes.

| Informação | Evidência implementada | Limite explícito |
|---|---|---|
| UID próprio | 12020/0x0202 result=0, u64 em payload+2 | UID de aparição isolada não estabelece dono |
| Nome, nível, diamantes | 12020/0x0305 prefixo UID/nome UTF16; nível após nome; diamantes +38 | Exige UID igual ao próprio |
| Classe/Biosuit | 0x0305 shapes exatos e 0x1304 sucesso; catálogo biosuits | Classe desconhecida se ID não catalogado |
| Rover | 0x0305 shapes exatos e 0x1403 sucesso | ID numérico; nome não inventado |
| CP | 12010/0x0401 payload786 offset772; 12010/0x0423 payload762 offset752; 12040/0x0401 | Requer `account_scoped=True` em fluxo atribuído à conta. Importador não adivinha ligação realtime; CP pode não observado |
| Diárias totais /10 | Limite10 solicitado pelo usuário | **Total concluído e restante ainda desconhecidos.** Tipo11 é só conclusão instantânea; não calcula10−instantâneas |
| Android Junkyard | moeda básica20 + recarga19 | Snapshot observado, sem contagem regressiva inventada |
| Secret Nemesis Base | básica22 + recarga21 | Mesmo limite |
| Exclusive Mining Field | básica54 + recarga53 | Mesmo limite |
| Public Mining Field | básica58; recargas Accretia55/Bellato56/Cora57 | Exibe separadas; facção não inferida nem recargas somadas |
| Localização | resposta12020/0x0325 result0: mapa payload+22; posição +27 apenas teleport_kind7 | Último destino confirmado, não movimento contínuo |

Tempos: snapshot 0x0305 apenas `len(payload)-name_end`1057/1065; moedas i em `name_end+22+(i−1)*8`, signed64. Atualização 0x0407 `<HIq>` é saldo absoluto. Negativos viram ausentes. Biosuit/rover de aparição apenas caudas comprovadas988/996/1004/1012, offsets relativos ao fim do nome829/834. Cada campo tem fonte e timestamp; perder dados não converte ausente em zero. API mantém quantidade fixa de campos, não histórico ilimitado.

## Importação passiva

`inspect_capture(path)` retorna candidates e diagnostics. Cada candidato contém account_id, auth_host/game_host, world_id, records e provenance (arquivo e conexões). JSON/JSONL e PCAP clássico IPv4/TCP Ethernet, RAW ou loopback NULL são aceitos. PCAPNG, IPv6, VLAN e fragmentação não são convertidos silenciosamente; formatos incompatíveis/fragmentados geram erro ou diagnóstico. Gaps TCP e retransmissão conflitante invalidam o fluxo; SYN separa reutilizações de conexão. Frame truncado é diagnosticado.

Login e jogo se associam por igualdade exata de account_id e session_key, nunca pelo primeiro pacote global. Reuso da credencial em logins diferentes bloqueia preparação por ambiguidade; várias conexões game geram candidatos para seleção explícita. Sem identidade de conexão, frame é ignorado com diagnóstico. World ID vem de12000/0x0107; ausência ou divergência exige override, sem default1.

`prepare_candidate(candidate, overrides)` retorna config,session,provenance,dashboard. Preserva campos desconhecidos; remove u64@2688 dependente da nova conexão. Template0x0201 só se válido contra conta e JWT. Nenhuma conexão de rede é aberta. A API não grava arquivos; CLI escreve após toda validação. Autenticação expirada somente poderá ser verificada em uso real.

## Validação local

`python -m unittest tests.test_capture_import tests.test_dashboard -q`
12 testes: duas contas, seleção real de World ID, ausência/ambiguidade, formato de dump vivo, PCAP segmentado/gap/truncado, dono versus terceiros, sucesso/rejeição de entrada, saldo zero, timers/updates absolutos, diárias parciais, Biosuit/classe/Rover/localização e CP exigindo atribuição explícita.

Não houve conexão real ao jogo nem compra. Restam validação com capturas atuais em uso e contrato confirmado para **total** diário e ligação inequívoca das portas realtime antes de habilitar CP automaticamente em importações multicontas.

## Replay real somente leitura

Verificado `login-session-20260923-011050.pcap` local: 1 candidato, 538 frames associados, zero diagnóstico de remontagem, 21 campos de sessão preparados; device_info permanece string. Hosts e World ID extraídos; resposta0x0108 confirmou o World ID pedido. Nome/UID/nível/diamantes, quatro tempos e instantâneas diárias observados. A cauda0x0305 dessa captura é1019 (após prefixo), fora das variantes comprovadas de equipamento: Biosuit/classe/Rover continuam ausentes até validação desse layout. IP anunciado pela resposta é diferente do endpoint12020 capturado; usa-se o destino TCP observado.

Outras capturas próximas010303 e000934 não contêm login completo reconhecido e não geraram candidatos. Não houve conexões de rede no replay nem impressão de credenciais. Novo teste bloqueia World ID divergente entre pedido/resposta. Suíte atual:14 testes aprovados.
