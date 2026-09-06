# RF Next Companion 2.0.0-beta.40

Instalador imutável para Windows x64 com a API Pktmon de streaming disponível.

- Identidade confirmada vinculada ao PID e ao horário de criação do cliente.
- Intervalos sem TCP não apagam o personagem; processos encerrados são removidos
  individualmente, sem afetar os outros clientes.
- Proteção contra reutilização de PID/porta e contra eventos atrasados que
  recolocariam clientes encerrados na tela.
- Correlação completa de equipamentos equipados para envio ao site.
- Correção da disputa entre pausa e retomada rápida da mesma sessão.

PID não confirma personagem sozinho. A proteção contra UIDs conflitantes foi
mantida; não há seleção manual nem exposição do PID no contrato do site.

Código-fonte validado: `37854f2` na branch `feat/rf-qol-web-based`.
Regressão: 609 testes, sem falhas, 1 ignorado; testes específicos: 21 aprovados.
Simulação de 14 horas preservou nome e duração. Isso não substitui um ensaio
real prolongado com o jogo aberto.

O manifesto Ed25519 está em `update-manifest.json`; `latest.json` é uma cópia
para validação isolada desta branch. O pacote não usa Authenticode.
