# Cliente RF NEXT v37

Execute `run-client.bat` após extrair o ZIP. Esta versão mantém as dependências anteriores, sem instalar outro framework de interface.

## Interface

Navegação lateral, fundo cinza, painéis escuros e texto branco inspirados na referência fornecida. Em Configuração, ajuste o tamanho da fonte entre 8 e 20; a escolha fica em `ui-settings.json`. Usa Arial Rounded MT Bold quando instalada, com Segoe UI como alternativa.

- Captura: coletas, consultas independentes, heartbeat, progresso e envio ao Companion.
- Ranking: personagens do ranking EXP.
- Mercado: escolha Local ou Global, procure um produto, expanda seus refinos e selecione um para ver as ofertas. O nome do vendedor vem da correspondência exata entre PCID e character_uid de um ranking validado; ambiguidades permanecem sem nome.
- Compras: lista local, lista recebida do site e execução.
- Configuração: parâmetros, aparência, compra manual e diagnóstico TX/RX com payloads completos.

## Lista de compra

Selecione uma oferta detalhada no Mercado e adicione à lista. Cada entrada representa o lote integral daquela oferta. A lista fica em `purchase-list.json` e sobrevive ao encerramento do programa.

Para executar, tenha uma captura atual, escolha Heartbeat ativo ou Nova conexão e revise a confirmação com ofertas, quantidades e preços. O primeiro modo usa o worker ativo; o segundo reutiliza o fluxo existente por oferta. Não há execução automática ao abrir o programa nem repetição automática de uma compra. A lista para no primeiro resultado não confirmado.

Pedidos em andamento ao encerrar tornam-se não confirmados na próxima abertura. O histórico de tentativas é preservado; apenas entradas preparadas podem ser removidas. Reservas de quantidade de propostas do site também persistem. O preço exibido é SellingPrice bruto; sua interpretação unitário/lote para quantidades maiores que um ainda depende de comprovação real.

## Site

Servidor padrão: https://apirf.karvalho.dev.br. A lista do site mantém o contrato em `CONTRATO-LISTA-COMPRAS-SITE.md`. Receber ou preparar propostas não compra. A rota de recebimento segue pendente de publicação no site; esta versão não altera nem publica o backend. A execução não atualiza automaticamente o saldo comprado no site.

## Validação

Testes automatizados aprovados, com detalhes em `VALIDACAO-v37.md`. Não foram realizadas compras reais durante o desenvolvimento. A validação visual final no computador de uso permanece manual.
