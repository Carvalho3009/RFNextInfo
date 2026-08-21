# RF QOL 2.0.0-beta.2 — Beta público

Instalador beta isolado da versão 2.0. Ele usa pasta, registro, atalhos e estado
de licença próprios, sem substituir a instalação estável nem a de homologação.

## Download

- `RF QOL Setup 2.0.0-beta.2 Beta.exe`
- SHA-256: `7CE42C401B60C0B04A625B4F7E4B423E1609AEF6A03F4EFCEF807A1B7DC9BD6D`
- Authenticode: `NotSigned`

## Correções deste beta

- restaura o acompanhamento das rotas quando processos ou conexões dos clientes
  são substituídos durante uma sessão;
- realinha novas rotas pelo UID canônico antes de atribuir EXP, contribuição e
  recompensas, evitando mistura entre clientes;
- recupera dados de bancos afetados quando o evento sem dono compartilha o
  mesmo fluxo TCP de uma identidade canônica única;
- mantém eventos ambíguos sem atribuição em vez de adivinhar o cliente.

## Validação automática

- 402 testes aprovados;
- casos específicos com dois clientes, rotação de processos, EXP, contribuição
  e recompensas aprovados;
- validação em cópia do banco real de longa duração aprovada;
- autoteste do executável empacotado aprovado;
- instalação silenciosa em pasta temporária aprovada;
- autoteste pós-instalação com `self_test=0`;
- desinstalação aprovada e executável removido;
- dependências verificadas com `pip check`;
- SBOM, checksum e procedência incluídos.

Esta é uma versão beta. Ensaios manuais, visuais, com múltiplos clientes e de
longa duração continuam sob responsabilidade dos testadores.
