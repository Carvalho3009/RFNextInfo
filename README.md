# RF QOL 2.0.0-rc1 — Homologacao

Instalador isolado para testes da versão 2.0. Ele usa a pasta, o registro, os
atalhos e o estado de licença de homologação, sem substituir a instalação RF
QOL normal.

## Artefato

- `RF QOL Setup 2.0.0-rc1 Homologacao.exe`
- SHA-256: `1EAC8C1E57366DA1FC0F6623F18B4756252AC6BA555102B96F139C46623979E6`
- Authenticode: `NotSigned`

## Validação automática

- 396 testes aprovados;
- atualização dos cartões e monitores validada sem a falha de carregamento;
- rotação automática por duração restaurada, preservando encerramentos por
  teleporte, morte e inatividade sem iniciar outra subsessão;
- autoteste do executável empacotado aprovado;
- instalação silenciosa em pasta temporária aprovada;
- autoteste pós-instalação com `self_test=0`;
- desinstalação aprovada e executável removido;
- dependências verificadas com `pip check`;
- SBOM e procedência incluídos.

Este é um candidato de homologação. Os ensaios manuais, visuais, com dois
clientes e de longa duração permanecem sob responsabilidade do testador.
