# RF QOL 2.0.0-beta.6

Beta pública com correção dos travamentos recorrentes da interface durante
capturas longas e com banco de dados volumoso.

## Download

- [Baixar RF QOL Setup 2.0.0-beta.6 Beta.exe](https://github.com/Carvalho3009/RFNextInfo/raw/refs/heads/download/rf-qol-2.0.0-beta.6/RF%20QOL%20Setup%202.0.0-beta.6%20Beta.exe)

## Correções desta versão

- a verificação de subsessões deixa de abrir o banco em modo de escrita a cada
  250 ms quando não existe encerramento pendente;
- a atualização do mapa deixa de recalcular combate, status e drops antes da
  frequência configurada para esses monitores;
- jogadores próximos reutilizam os mesmos componentes visuais enquanto os
  dados não mudarem;
- banco, capturas, sessões e configurações existentes são preservados.

## Verificação

- SHA-256: `AADF53F778910CB5EF201E1975F62E1F58A88D2EA1237917BB96C7841EC0DA30`
- tamanho: `54.082.725 bytes`
- regressão automática: `415 testes aprovados`;
- instalador público: instalação silenciosa, autoteste e desinstalação
  aprovados;
- Authenticode: `NotSigned`.

O hash do `installer-smoke-result.json` pertence ao instalador temporário de
ensaio, recompilado do mesmo código e perfil. O hash do instalador público é o
registrado acima e no arquivo `.sha256.txt`.

## Artefatos

- instalador e checksum;
- procedência do build limpo;
- resultado do ensaio do instalador;
- SBOM das dependências Python;
- lockfile e termos de uso.
