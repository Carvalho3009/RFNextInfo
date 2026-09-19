# Cliente de Mercado para RF Companion — 19/09/2026

## Atualização local/global

[Baixar cliente local/global](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-market-client-20260919/rfnext-market-local-global-20260919.zip).

Consultas, detalhes, relatórios e envio separados por mercado e item. Inclui catálogo SQLite e instruções de uso. Validação local: 184 testes, 177 aprovados e 7 ignorados. Os seletores de envio global ainda são hipótese; confirmação no jogo pendente. O cliente rejeita respostas de mercado divergente. Esta atualização não altera o receptor publicado. O pacote anterior permanece disponível abaixo.

Distribuição em código-fonte para Windows, Python 3.10+ com Tkinter. Instale requirements.txt e execute run-client.bat conforme README do ZIP. Não é instalador independente de Python.

Interface com coleta e envio separados, consulta agregada e ofertas detalhadas, fila persistente e envio assinado ao Companion. Configure o destino https://apirf.karvalho.dev.br e faça o vínculo da instalação conforme as instruções. Não inclui configurações, credenciais, resultados ou estado de usuários. Credenciais do jogo não são enviadas ao Companion.

Preserve sua configuração, sessão, resultados e pasta companion.state_dir fora da pasta substituída. Não mova identidade DPAPI entre computadores/usuários. O pacote não instala nem ativa envio automaticamente.

Validação local: 179 testes, 172 aprovados e 7 ignorados; extração, ajuda e compilação verificadas. Receptor integrado validado separadamente. Sem homologação de jogo real ou Windows 10 físico. Raw conserva a representação disponível do decoder; a projeção agregada legada usa inteiros.
