# v36 — resultados no programa e lista de compras

Abra run-client.bat. A interface foi reorganizada em Mercado, Rankings, Compras, Configurações e Diagnóstico. Parar tudo está disponível no cabeçalho.

## Mercado e Rankings

Consulte o mercado e veja produtos e ofertas na própria janela. Selecione Local ou Global, busque nome/ID e filtre refino. A tabela mostra quantidade do lote, preço informado, vendedor quando identificado, PCID, ID da oferta e datas disponíveis. A captura exibe horário de recebimento e estado, incluindo resultado parcial. Rankings aparecem em tabela própria após consulta.

Configurações, consultas contínuas separadas, intervalos após encerramento, heartbeat e upload permanecem disponíveis. Mensagens TX/RX, credenciais e payloads completos continuam acessíveis em Diagnóstico e na exportação.

## Compras

1. Use a instalação já vinculada ao site, em Configurações / Companion.
2. Na aba Compras, clique Receber lista do site. A lista existente no site é a origem; nenhuma segunda lista é criada no servidor.
3. Faça uma consulta de mercado. Escolha Local ou Global em Compras e clique Preparar ofertas.
4. Revise os lotes propostos. O programa preserva os IDs, não divide lotes, não ultrapassa a quantidade desejada e não usa a mesma oferta duas vezes. Itens sem oferta compatível aparecem como pendentes.
5. Se desejar executar, selecione uma proposta e um dos dois modos de compra. Confira nome, quantidade, oferta, vendedor, preço e refino na confirmação.

Receber/preparar não envia pedidos de compra ao jogo. A execução reutiliza a verificação 0x0215/0x0216 e a compra única 0x1D12/0x1D13. No modo heartbeat ativo, utiliza o mesmo socket já validado na v35. Nova captura/lista invalida propostas anteriores. Uma oferta tentada fica bloqueada durante a execução do programa; esse bloqueio não persiste após reiniciar. Não há repetição automática nem atualização automática do status comprado na lista do site.

O preço de referência do site não é teto de gasto. SellingPrice é exibido e enviado bruto: a interpretação unitário/lote para quantidades maiores que um ainda não foi comprovada por compra real. As propostas não garantem disponibilidade atual; o servidor decide no envio.

Compras iniciadas pela lista reservam localmente a quantidade do respectivo item. Sucesso ou resultado incerto mantém a reserva; rejeição ou bloqueio comprovados liberam a quantidade. Novas capturas e sincronizações não apagam essas reservas durante a execução do programa. Assim, preparar novamente não propõe unidades já compradas ou ainda sem confirmação. O saldo do site não é alterado automaticamente; as reservas locais terminam ao fechar o programa.

## Integração do site

O recebimento exige a rota POST /api/qol/v1/agent/shopping/sync no site. A implementação está no commit local 4fef20a do RF QOL Web e no patch site-shopping-v36.patch distribuído com os arquivos de publicação. Até publicar essa rota, a sincronização no servidor público pode responder 404; isso não significa lista vazia.

Contrato assinado Ed25519 com a identidade existente. O site entrega somente os itens ativos do proprietário vinculado, descontando as quantidades já compradas. Nenhuma credencial de sessão do jogo é enviada por essa sincronização.

Validação visual e uso real da nova interface permanecem manuais. A v36 não realizou compras reais durante o desenvolvimento.
