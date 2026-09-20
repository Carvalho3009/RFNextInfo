# v26 — repetição após encerramento do ciclo

[Baixar v26](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919-v26.zip).

Na execução contínua, erros de um ciclo são registrados e não desativam a execução. O intervalo configurado começa somente quando o ciclo termina, inclusive após falha; a próxima tentativa só começa depois desse intervalo. A autenticação e a conexão inicial continuam sendo falhas fatais. Testes da consulta completa: 6 aprovados.

# v11 — exportador completo incluído

[Baixar v11](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919-v11.zip).

Arraste o PCAP principal sobre converter-captura.bat; use o .completo.json no preparador com --initialize-character. Conversão e preparação do 0201 validadas offline na captura real 20260919-171931. Não recupera comandos ausentes no PCAP nem renova credenciais. Cliente mantém a implementação v10.

# Atualização v10 — entrada experimental do personagem

[Baixar v10](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919-v10.zip).

Opção --initialize-character no preparador. Exige novo dump com 0x0201; atualiza identificadores da conexão e aguarda 0x0202 antes do mercado. Desativada sem configuração explícita. Leia instruções do ZIP e preserve configuração/vínculo em pasta separada. Testes: 199 executados, 192 aprovados e 7 ignorados; reconstrução idêntica à captura de referência. Inicialização ativa e efeito sobre rankings ainda pendentes.

# Atualização v9 — sequência de rankings

[Baixar v9](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919-v9.zip).

EXP: 0x1A03 seguido de 0x1A01 sem aguardar resposta intermediária. Facções: agenda 0x2408 e seletores 0101/0201/0301, correlacionando listas completas. Timeout isolado não bloqueia as outras listas. Preserva envio, cruzamento de vendedores e barras. Validação: 198 testes (191 aprovados, 7 ignorados) e 15 quadros reais das duas capturas mais recentes. Teste ativo no jogo pendente. Preserve configuração, sessão e pasta companion.state_dir.

# Atualização v8 — vendedores pelos rankings

[Baixar v8](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919-v8.zip).

Cruza IDs exatos da mesma coleta para preencher seller nos mercados local e global. Usa as 300 posições de EXP e três rankings de facção. Nomes conflitantes ou ausentes continuam desconhecidos. Faça nova coleta com rankings e envio habilitados; não reescreve lotes antigos. Preserve configuração, sessão e companion.state_dir. Testes: 198 executados, 191 aprovados e 7 ignorados.

# Atualização v7 — barras de progresso

[Baixar v7](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919-v7.zip).

Barras de leitura por etapa e envio por lotes confirmados pelo receptor, sem mensagens de progresso por item na interface. Rejeições continuam visíveis. Preserve configuração, sessão e pasta companion.state_dir. Validação automatizada: 197 testes, 190 aprovados, 7 ignorados. Visualização manual pendente.

# Atualização v6 — envio de rankings

[Baixar v6](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919-v6.zip).

Integra os contratos community.exp_ranking_snapshot e community.faction_ranking_snapshot à mesma fila e identidade do mercado. Envia Top 100 de EXP e cada facção; conserva 300 posições de EXP no dump local. Rankings inválidos/incompletos geram diagnóstico local. Preserve config, sessão e companion.state_dir.

Validação: 195 testes, 188 aprovados e 7 ignorados; quatro lotes completos passaram no validate_batch do receptor. Sem envio de dados de teste ao site.

# Atualização v5 — rankings

[Baixar v5](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919-v5.zip).

Consulta EXP (300 posições) e Top 100 de Accretia, Bellato e Cora após o mercado. Ativo por padrão na interface; terminal: `"rankings": true` no config. Salva os rankings no JSONL local; ainda não envia rankings ao Companion. Preserve config, sessão e a pasta companion.state_dir para manter o vínculo.

Validação: 192 testes (185 aprovados, 7 ignorados); os 300 registros de uma resposta real de EXP coincidem com o decoder. Teste ativo no jogo pendente.

# Cliente de Mercado para RF Companion — 19/09/2026

## Atualização local/global

[Baixar v4 — envio completo corrigido](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919-v4.zip).

Corrige o envio de mercados com mais de 32.768 ofertas: até 256 partes de ofertas, sem misturar mercados ou dividir uma coleta em snapshots concorrentes. Listas agregadas respeitam 256 linhas por parte. Receptor atualizado em 19/09 às 18:33 (Brasília), preservando preço máximo zero informado pelo jogo. Validação: 189 testes do cliente (182 aprovados, 7 ignorados), 47 testes do receptor e envio assinado em banco isolado de 114 lotes com 49.219 ofertas locais e 2.324 globais. Não houve reenvio da coleta do usuário para produção. Prefira v4 aos pacotes abaixo.

[Baixar v3 — conexão aberta após coleta](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919-v3.zip).

Na interface, mantém a conexão 12020 aberta após concluir e enviar a coleta. Resultado disponível para exportação; botão Desconectar encerra a sessão. Fechamento pelo servidor preserva a coleta. Não implementa ainda heartbeat 0x0205 ou renovação de token; permanência da sessão depende do servidor. CLI permanece execução única. Validação: 187 testes, 180 aprovados e 7 ignorados; sem teste de permanência no jogo real. Prefira v3 aos pacotes abaixo.

[Baixar correção v2](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919-v2.zip).

Correção baseada na captura 20260919-163618: lista global usa `0100`, não `0001`. Duas consultas reais confirmam a resposta do mercado 1. A captura não contém detalhes nem entrada na 12000; o seletor dos detalhes e a causa do timeout de entrada permanecem pendentes. 177 testes aprovados, 7 ignorados. Prefira a v2 aos pacotes abaixo.

[Baixar cliente local/global](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919.zip).

Consultas, detalhes, relatórios e envio separados por mercado e item. Inclui catálogo SQLite e instruções de uso. Validação local: 184 testes, 177 aprovados e 7 ignorados. Os seletores de envio global ainda são hipótese; confirmação no jogo pendente. O cliente rejeita respostas de mercado divergente. Esta atualização não altera o receptor publicado. O pacote anterior permanece disponível abaixo.

Distribuição em código-fonte para Windows, Python 3.10+ com Tkinter. Instale requirements.txt e execute run-client.bat conforme README do ZIP. Não é instalador independente de Python.

Interface com coleta e envio separados, consulta agregada e ofertas detalhadas, fila persistente e envio assinado ao Companion. Configure o destino https://apirf.karvalho.dev.br e faça o vínculo da instalação conforme as instruções. Não inclui configurações, credenciais, resultados ou estado de usuários. Credenciais do jogo não são enviadas ao Companion.

Preserve sua configuração, sessão, resultados e pasta companion.state_dir fora da pasta substituída. Não mova identidade DPAPI entre computadores/usuários. O pacote não instala nem ativa envio automaticamente.

Validação local: 179 testes, 172 aprovados e 7 ignorados; extração, ajuda e compilação verificadas. Receptor integrado validado separadamente. Sem homologação de jogo real ou Windows 10 físico. Raw conserva a representação disponível do decoder; a projeção agregada legada usa inteiros.
