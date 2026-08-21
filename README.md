# RF QOL 2.0.0-beta.3

Beta pública para validação das correções de monitoramento e da interface 2.0.

## Download

- [Baixar RF QOL Setup 2.0.0-beta.3 Beta.exe](https://github.com/Carvalho3009/RFNextInfo/raw/refs/heads/download/rf-qol-2.0.0-beta.3/RF%20QOL%20Setup%202.0.0-beta.3%20Beta.exe)

## Principais correções

- recuperação das rotas dos clientes após retomar a captura ou reiniciar o jogo;
- monitor de vida do Boss e atividade de Farm separados corretamente por cliente;
- Rover recuperado pelo último estado confirmado quando necessário;
- contribuição por hora do Resumo Geral atualizada a cada minuto;
- XP exibida no formato `valor bruto (%)`;
- Visão Geral reorganizada para aproveitar melhor o espaço disponível.

## Verificação

- SHA-256: `A014DBC877A60102DD5F9DAA622884D8BA731EF98366CC9BA007C4F776F41957`
- tamanho: `54.082.729 bytes`
- regressão automática: `406 testes aprovados`
- ensaio do instalador: instalação silenciosa, autoteste e desinstalação aprovados;
- Authenticode: `NotSigned`.

O hash do `installer-smoke-result.json` pertence ao instalador temporário de
ensaio, recompilado do mesmo commit e perfil. O hash do instalador público é o
registrado acima e no arquivo `.sha256.txt`.

## Artefatos

- instalador e checksum;
- procedência do build;
- resultado do ensaio do instalador;
- SBOM das dependências Python;
- lockfile e termos de uso.

