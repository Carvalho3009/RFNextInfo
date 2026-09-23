# v35 — duas opções de compra

Abra run-client.bat. Informe os seis campos atuais da oferta e confira os valores na confirmação.

- **Comprar: nova conexão**: autentica, inicializa o personagem, confirma heartbeat, verifica o dispositivo e solicita a compra. Pare consultas e heartbeat antes deste modo.
- **Comprar: heartbeat ativo**: usa o mesmo socket do worker após três confirmações. Não autentica nem inicializa novamente. Pare as consultas; mantenha o heartbeat ligado.

Ambos enviam 0x0215 vazio e só liberam 0x1D12 após 0x0216 com ret=0 e verification=1. Falha, timeout ou resposta inválida na verificação bloqueiam a compra. Isso consulta a verificação existente; não substitui cadastro/autenticação de dispositivo exigido pelo jogo.

No modo heartbeat, o próprio worker processa o pedido e recebe as respostas; não há dois leitores concorrendo pelo socket. Continua enviando 0x0205 durante as esperas e retoma seu ciclo após o resultado.

O pedido compra uma oferta; não há quantidade parcial. Nenhuma compra é repetida automaticamente. Só há confirmação com 0x1D13 válido, códigos de sucesso e correspondência de mercado, oferta, vendedor, preço, item e refino. Perder a resposta depois do envio deixa o resultado não confirmado; confira o jogo antes de tentar novamente.

Os botões de compra não consultam mercado/ranking nem enviam ao Companion. Os quadros e o resultado aparecem no log exportável. Parar tudo encerra também o heartbeat; não desfaz uma compra já enviada.

Fluxo baseado na captura login-session-20260923-011050.pcap: 0x0215 → 0x0216 (000001) → 0x1D12 → 0x1D13 com sucesso. Validação desta implementação foi local, sem compra real e sem teste visual.
