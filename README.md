# RF Next Companion 2.0.0-beta.49

Corrige o envio dos requisitos entregues e faltantes de Coleção ao Companion.
Inclui o catálogo no pacote do Agent e respeita a quantidade exigida por requisito.
Referência com 4.785 coleções e 14.458 requisitos.

[Baixar instalador](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-agent-2.0.0-beta.49/RF-Next-Companion-Setup-2.0.0-beta.49.exe)

Sequência 59 do canal beta. Manifesto e procedência assinados com Ed25519.
Regressão: 670 testes, 2 opcionais ignorados, sem falhas. Autoteste do executável,
ensaio isolado de instalação/atualização/remoção e integração com o planejador aprovados.

A atualização preserva identidade, histórico e fila. É necessária uma nova captura
válida para atualizar o progresso antigo sem posições. Coleções não recebidas
continuam desconhecidas. A beta.48 permanece na referência original.
Reverter o canal suspende a oferta, mas não faz downgrade automático.
