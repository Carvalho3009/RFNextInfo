# RF QOL 2.0.0-rc1 — Homologacao

Instalador isolado para testes da versão 2.0. Ele usa a pasta, o registro, os
atalhos e o estado de licença de homologação, sem substituir a instalação RF
QOL normal.

## Artefato

- `RF QOL Setup 2.0.0-rc1 Homologacao.exe`
- SHA-256: `74F6709E161DA5FFE1CD345CB461DF707E0945AD7F1EDAF66D7435D3755F4B4F`
- Authenticode: `NotSigned`

## Validação automática

- 377 testes aprovados;
- autoteste do executável empacotado aprovado;
- instalação silenciosa em pasta temporária aprovada;
- autoteste pós-instalação com `self_test=0`;
- desinstalação aprovada e executável removido;
- dependências verificadas com `pip check`;
- SBOM e procedência incluídos.

Este é um candidato de homologação. Os ensaios manuais, visuais, com dois
clientes e de longa duração permanecem sob responsabilidade do testador.
