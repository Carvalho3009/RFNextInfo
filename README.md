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
