# RF QOL 2.0.0-rc1 — Homologacao

Instalador isolado para testes da versão 2.0. Ele usa a pasta, o registro, os
atalhos e o estado de licença de homologação, sem substituir a instalação RF
QOL normal.

## Artefato

- `RF QOL Setup 2.0.0-rc1 Homologacao.exe`
- SHA-256: `C778DF9B489C5F8E40334E7E937EF4A74268F600E09DA3DB638923E36BD28B53`
- Authenticode: `NotSigned`

## Validação automática

- 384 testes aprovados;
- autoteste do executável empacotado aprovado;
- instalação silenciosa em pasta temporária aprovada;
- autoteste pós-instalação com `self_test=0`;
- desinstalação aprovada e executável removido;
- dependências verificadas com `pip check`;
- SBOM e procedência incluídos.

Este é um candidato de homologação. Os ensaios manuais, visuais, com dois
clientes e de longa duração permanecem sob responsabilidade do testador.
