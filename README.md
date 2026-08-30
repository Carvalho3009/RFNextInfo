# RF Next Companion 2.0.0-beta.29

Instalador imutável da versão beta.29 do RF Next Companion para Windows x64.

Esta versão dá prioridade máxima ao processamento local dos eventos de Boss e
expõe, na API local de Boss, a associação dos personagens com suas guildas por
`guild_id` e `guild_name`, mantendo o campo legado `guild` para compatibilidade.
Os eventos de Boss e PvP continuam restritos à API local e não são enviados ao
site.

O manifesto Ed25519 está em `update-manifest.json`; `latest.json` é uma cópia
para validação isolada desta branch.

