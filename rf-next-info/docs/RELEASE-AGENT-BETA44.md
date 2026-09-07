# RF Next Companion 2.0.0-beta.44

Sequencia de atualizacao: 54. Estado inicial: preparacao autorizada pelo owner.

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

Publicacao exige regressao, replay, self-test do executavel, ensaio isolado do
instalador, hashes, procedencia e manifesto Ed25519 verificados. Sem Authenticode,
sem UPX, sem bypass/exclusao de antivirus. Captura atual nao deve ser interrompida.
