# RF Next Companion — canal beta

Oferta atual: **2.0.0-beta.64 / sequência74**. Identificação passiva de mundo por confirmação de login e personagem na mesma conexão; leituras complementares RFXuonz integradas, preservando as funções anteriores.

`latest.json` é o manifesto Ed25519 da beta.64; `previous-latest.json` preserva beta.63/seq73. O instalador está no download versionado indicado no manifesto.

803 testes:801 aprovados e2 ignorados; pipeline isolado, autoteste empacotado e instalador DEV_SMOKE aprovados. A captura real da beta.64 ainda aguarda instalação pelo usuário. Publicação não instala nem reinicia o Agent. Após instalar, inicie a captura antes de entrar no personagem para observar as confirmações de mundo/UID. Ausência ou conflito mantém origem desconhecida.

Reversão da oferta por novo commit, preservando mudanças concorrentes. Clientes que já aceitaram sequência74 não fazem downgrade automático para73. Sem Authenticode conforme política do produto; manifesto e procedência Ed25519 acompanham a entrega.
