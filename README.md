# RF QOL 2.0.0-beta.1 — Beta público

Instalador beta isolado da versão 2.0. Ele usa pasta, registro, atalhos e estado
de licença próprios, sem substituir a instalação estável nem a de homologação.

## Download

- `RF QOL Setup 2.0.0-beta.1 Beta.exe`
- SHA-256: `11177B11F44997325E6E171B7463D0239B8A67382E8F08F490915D3E48C2E357`
- Authenticode: `NotSigned`

## Destaques deste beta

- anúncios de aprimoramento e prime deixam de entrar no histórico de drops de
  outros jogadores;
- alertas de drop podem combinar raridade com Arma, Armadura, Acessório,
  Expansão, Skill, Blueprint MAU e Blueprint Launcher;
- Ranking de EXP exporta o ranking atual ou o histórico filtrado em CSV;
- licenças V3 e módulos beta liberados para as licenças RF QOL ativas;
- envios sanitizados para o site, incluindo Ranking de EXP, observações e Banco
  de Leilão, com validação de licença e deduplicação.

## Validação automática

- 399 testes aprovados;
- regressão completa de captura, status, subsessões, mapas, monitores, interface,
  licença e integrações aprovada;
- autoteste do executável empacotado aprovado;
- instalação silenciosa em pasta temporária aprovada;
- autoteste pós-instalação com `self_test=0`;
- desinstalação aprovada e executável removido;
- dependências verificadas com `pip check`;
- SBOM e procedência incluídos.

Esta é uma versão beta. Os ensaios manuais, visuais, com múltiplos clientes e de
longa duração ainda devem ser realizados pelos testadores.
