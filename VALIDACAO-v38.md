# Validação v38

## Executado

- Suite de regressão v37 e novos testes: `python -m unittest discover -s tests -q`: 297 testes, 290 aprovados e 7 ignorados, em 17,35 segundos.
- Persistência testada com 210 perfis, sem teto artificial; geração atômica de config/sessão, falha em cada etapa de gravação, migração repetida e preservação do vínculo Companion.
- Integração com duas threads reais e transporte simulado: A continua ligada ao próprio heartbeat enquanto B está selecionada; parar A não para B; filas, arquivos de compras e dashboard não se misturam.
- Rejeição de identidade duplicada, configuração de outra conta, alteração de sessão ativa e atualização com eventos pendentes.
- Reserva persistente da lista do site por diretório, instalação e shopping_id, inclusive após reinício.
- Encerramento sem iniciar novas consultas; tratamento de falha permanente ao salvar dashboard com decisão explícita do usuário.
- Shell testado sem janela: seis páginas, contexto do perfil, escala de fonte, navegação e callbacks da v37.
- Pacote extraído fora da árvore de módulos original: 62 testes direcionados aprovados (perfis, importação, dashboard, concorrência, shell, consulta completa e compras). CRC e exclusão dos arquivos locais conferidos.
- PCAP real `login-session-20260923-011050.pcap`: 1 candidato, 538 frames, 21 campos de sessão preparados, hosts e mundo identificados, zero diagnóstico de remontagem. Nenhuma credencial foi usada para conectar.
- Importação sintética: duas contas, seleção de mundo, resposta divergente, retransmissão, gap/truncamento, horários e proveniência de revisão manual.
- Dashboard: identidade própria versus outros jogadores, valores zero, snapshots e atualizações de timers, diárias parciais, equipamento, destino e exigência de atribuição explícita para CP.

## Limites

Sete testes dependentes de capturas de referência permanecem ignorados quando essas capturas não estão disponíveis. Testes simulados não comprovam sessões reais duradouras, capacidade ilimitada de execução, nem aparência renderizada no computador do usuário.

Total diário, ligação automática do fluxo de CP e layouts de equipamento desconhecidos continuam pendentes, registrados no inventário. Não houve compra real, deploy do site nem controle de tela.

O agent-organizer definiu os escopos, implementou a frente visual e revisou a integração. Dois workers Python implementaram perfis e importação/decoder; o agente principal integrou e testou. O limite de threads impediu revisores visuais especializados separados; não se afirma revisão independente por ui-designer/accessibility-tester.

O ZIP deve passar por CRC, igualdade dos fontes incluídos e testes após extração. A distribuição exclui dados de contas, preferências e bancos locais. SHA-256 do download deve coincidir com SHA256SUMS.txt.
