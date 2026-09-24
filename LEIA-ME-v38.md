# RF NEXT Companion v38 — várias contas

Extraia o ZIP e execute `run-client.bat`. As dependências são as mesmas da v37: Python com Tkinter e cryptography. Não é necessário instalar outro framework visual. O servidor Companion permanece https://apirf.karvalho.dev.br.

## Contas e captura

Use **Importar PCAP** na barra superior, escolha a sessão detectada e salve o perfil. O programa identifica os IPs de login/jogo e o World ID observado; não assume mundo 1. Candidatos mostram conta, conexões e horários. Captura incompleta explica os campos ausentes; a revisão manual é registrada. A importação não conecta nem compra.

PCAP clássico IPv4/TCP e dumps JSON/JSONL são aceitos. PCAPNG, IPv6 e VLAN não são suportados nesta versão. Uma captura que não contenha autenticação suficiente não gera uma sessão utilizável.

Também é possível usar **Adicionar** para configurar manualmente. Não há teto fixo de contas cadastradas. Selecione uma conta para usar suas seis páginas; as outras continuam executando. Cada perfil possui controlador, heartbeat, cancelamentos, resultados e lista de compras independentes. As telas dos perfis são criadas conforme são abertas. O limite prático de execução depende do computador e do servidor.

Uma conta autenticada não pode executar em dois perfis da mesma instância. Configuração/sessão só muda após encerrar operações e processar seus eventos pendentes. Uma nova importação da mesma conta preserva o histórico, substitui a sessão e limpa a visualização dos resultados da sessão anterior.

## Dashboard e visual

Dashboard é a página inicial. A barra superior identifica a conta; o seletor é pesquisável. A navegação mantém Captura, Ranking, Mercado, Compras e Configuração. A fonte continua ajustável em Configuração, usando Arial Rounded MT Bold quando instalada, com Segoe UI como alternativa.

O dashboard apresenta os valores decodificados da própria conta, com origem e horário. Nome, nível, diamantes, classe/Biosuit/Rover, tempos das quatro dungeons e último destino confirmado aparecem quando a captura contém o layout reconhecido. Campo ausente permanece **Não observado**. O saldo de dungeon não vira uma contagem regressiva presumida; localização não representa acompanhamento contínuo do movimento.

**Pendências de dados:** o total das 10 missões diárias ainda não tem contrato comprovado; o contador de conclusões instantâneas aparece separado e não é usado para calcular esse total. CP automático depende de vincular com segurança o fluxo realtime à conta, o que esta importação ainda não faz. Alguns layouts de equipamento de capturas recentes também permanecem desconhecidos. Esses campos não são considerados integralmente entregues. Veja `INVENTARIO-DASHBOARD-v38.md`.

## Compras, envio e arquivos

Compras seguem os modos já existentes e confirmam explicitamente a conta. Lista local e histórico persistem por perfil; compras incertas nunca voltam automaticamente para preparadas. O programa impede que perfis/instalações diferentes executem novamente os mesmos IDs da lista do site. A reserva do perfil executor é persistente; trocar de conta ou reiniciar não a remove.

Os perfis ficam em `accounts/<id>/`. Configuração e sessão são publicadas juntas por uma referência atômica a uma geração; gerações anteriores permanecem preservadas. A migração copia os arquivos legados sem apagá-los e reutiliza o diretório Companion existente, preservando vínculo e sequência de envio. Não apague `accounts`, o banco de envios ou `site-executors.sqlite3` para tentar liberar compras.

Snapshots do dashboard têm tamanho limitado aos campos conhecidos e ficam em cada perfil. Fonte permanece em `ui-settings.json`. Credenciais e payloads continuam sem ocultação. A integração da lista do site permanece sujeita ao contrato e à disponibilidade da rota existente; nenhum backend foi publicado por esta versão.

## Validação e retorno à v37

Consulte `VALIDACAO-v38.md`. Não houve autenticação ao jogo nem compras reais durante o desenvolvimento. Avaliação visual e operação real com várias contas ainda precisam ser feitas no computador de uso.

Para retornar à v37, use o ZIP anterior em pasta separada com seus arquivos originais preservados. Não mescle listas de compras ou bancos de envio de perfis distintos.
