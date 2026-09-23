# v34 — teste de compra manual

Abra run-client.bat e use **Comprar oferta (teste)**. Pare consultas e heartbeat antes de iniciar. Informe mercado (0 local, 1 global), ExchangeIndex, PCID do vendedor, SellingPrice, ItemIndex e refino. IDs aceitam decimal ou hexadecimal com 0x. Revise todos os valores na confirmação.

É um registro de oferta por pedido; não há campo de quantidade parcial implementado. Use dados atuais da oferta. Os IDs da captura de exemplo não são preenchidos automaticamente.

O programa autentica, inicializa o personagem, confirma um heartbeat e envia 0x1D12 uma única vez. Esse acesso pode desconectar o jogo, como nos demais acessos ativos. Não executa consultas nem envio ao Companion nesse botão.

Só confirma a compra se receber 0x1D13 válido, códigos de sucesso e correspondência de mercado, oferta, vendedor, preço, item e refino. Timeout, resposta inválida ou desconexão após a tentativa ficam como não confirmado. Não repete automaticamente. Confira o jogo antes de decidir enviar outra compra.

O resultado e os quadros ficam no log exportável. Parar tudo antes do envio cancela; depois de iniciado o envio não desfaz uma compra.

Formato confirmado por purchase-latest-verify.md: u8 mercado + u16 quantidade de registros + registro u64 ExchangeIndex, u64 PCID, u64 SellingPrice, u32 ItemIndex, u16 EnchantLv, little-endian.

A captura original não contém 0x1D13. Esta versão foi validada localmente; nenhuma compra real foi executada pelo desenvolvimento.
