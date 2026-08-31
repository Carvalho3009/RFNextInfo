# RF Next Companion 2.0.0-beta.30

Instalador imutável da versão beta.30 do RF Next Companion para Windows x64.

Esta versão corrige o vínculo entre personagem e sessão quando o jogo abre uma
nova rota TCP entre duas verificações do Agent. A rota passa a ser resolvida no
primeiro pacote, evitando que EXP, contribuição, créditos, kills e drops sejam
projetados sem o personagem confirmado.

Também torna a fotografia dos anúncios pessoais autoritativa, permitindo
encerrar alertas de undercut de anúncios vendidos, removidos ou republicados
que já não aparecem na lista atual, sem apagar o histórico.

O manifesto Ed25519 está em `update-manifest.json`; `latest.json` é uma cópia
para validação isolada desta branch.
