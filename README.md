# RF Next Companion 2.0.0-beta.41

Instalador Windows x64. Requer a API Pktmon de streaming, como na beta.40.

- Corrige snapshots dos equipamentos equipados quando o perfil chega antes das
  referências ativas, inclusive correlação parcial e conexões diferentes.
- Preserva confirmação de personagem, separação entre clientes/sessões e deduplicação.
- Reforça a persistência da fila após interrupção de energia.

Código validado: `5234695cfac5b55e9be46a482195fb1cc735d82c`, branch
`release/rf-qol-agent-beta41`, PR #37.
134 testes específicos e 615 testes de regressão, sem falhas, 1 ignorado.
O autoteste do executável verifica a correlação parcial com referências tardias.
Pacote final aprovado no ensaio instalado e em 10 repetições do autoteste.

Atualização disponível pelo Companion. O instalador preserva vínculo, configurações
e fila local. Depois de atualizar, é necessária uma nova captura dos equipamentos
no jogo; snapshots descartados pela versão antiga não são recriados pela instalação.

Não inclui o suporte experimental do Windows 10. Não houve alteração no servidor.
Não usa Authenticode nem modifica antivírus. Manifesto e procedência Ed25519,
SHA-256 e evidências de build acompanham o instalador.
