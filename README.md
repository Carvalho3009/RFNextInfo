# Canal beta do RF Next Companion

`latest.json` é um manifesto Ed25519. O instalador permanece na branch da versão.
Este canal contém somente metadados públicos da distribuição.

Versão atual: `2.0.0-beta.52` (sequência 62).

[Baixar instalador](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-agent-2.0.0-beta.52/RF-Next-Companion-Setup-2.0.0-beta.52.exe)

Rotação lógica de sessão a cada seis horas, prioridade de dados de chefes,
localização confirmada e recibos aplicados atomicamente à fila local.
Preserve a pasta de dados do Agent e a fila durante a atualização.

Atualizações iniciadas pela beta.51 ou posterior salvam os vínculos das sessões
em arquivo protegido, com retomada em até 15 minutos para processos e conexões
preservados. Não há captura durante o intervalo em que o programa fica fechado.

Beta.51 e o manifesto anterior permanecem disponíveis para recuperação manual.
Restaurar o canal suspende a oferta, sem downgrade automático de instalações.
