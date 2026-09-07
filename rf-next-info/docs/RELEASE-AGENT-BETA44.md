# RF Next Companion 2.0.0-beta.44

Sequencia de atualizacao: 54. Publicada no canal beta em 07/09/2026 UTC,
com autorizacao do owner.

- Leitura dos layouts de equipamento com caudas de 1004 e 1012 bytes, mantendo
  988 e 996. Offsets conferidos na captura real de 04/09/2026.
- Referencia completa de oito bytes para correlacionar, preservar e marcar
  equipamentos. Corrige colisoes do antigo campo de slot e do UID abreviado.
- Linhas de equipment exportadas com indices unicos por snapshot; evita
  sobrescrita de itens tanto na fila do Agent como no receptor existente.
- Nenhuma mudanca de contrato de transporte ou migracao do site necessaria.
- Mantem as funcionalidades da beta.43, incluindo o caminho ETW do Windows 10.
  Nao foi realizado teste fisico em Windows 10 nesta entrega.

Evidencia funcional: replay privado de dois clientes gerou snapshots com 35 e
42 itens, 17 equipados por personagem. O codigo implantado do receptor aceitou
os lotes e exibiu ambos os loadouts em banco temporario isolado, sem rejeicoes.
Isso nao equivale a confirmar a chegada de uma captura nova em producao.

Detalhes: `DIAGNOSTICO-EQUIPAMENTOS-2026-09-07.md`.

## Publicacao validada

- Suite completa com replay real: 634 testes, sem falhas, 1 skip opcional
  preexistente; 91,796 s na preparacao do instalador.
- Self-test empacotado e ensaio isolado de instalacao, atualizacao e remocao OK.
- Decoder, bridge e perfil empacotados conferidos contra o codigo validado.
- Download publico, tamanho, SHA-256, manifesto e procedencia Ed25519 validados.
- Atualizador publico oferece beta.44 para sequencias 51, 52 e 53; nao oferece
  atualizacao repetida para a sequencia 54.
- Codigo: `0cdea0fb18e0a7e50308d90eeb39001dfe6e7564`.
- Instalador: 35.738.757 bytes; SHA-256
  `d1f0f7300205c6acb1cf19951f791759ad6c844f193b338d35118a44baf65f40`.

[Instalador publico](https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-agent-2.0.0-beta.44/RF-Next-Companion-Setup-2.0.0-beta.44.exe)

Sem Authenticode, UPX ou bypass/exclusao de antivirus. A captura atual nao foi
interrompida nem atualizada automaticamente. Falta confirmar uma captura nova
de equipamentos no site apos aplicar a atualizacao. Nenhum receptor foi alterado.

Rollback: a beta.43 e o manifesto anterior foram preservados. Restaurar o feed
anterior apenas suspende novas ofertas; nao rebaixa instalacoes ja atualizadas.
Custo real: unknown.
