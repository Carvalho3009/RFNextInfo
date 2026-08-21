# RF QOL 2.0.0-beta.5

Beta pública com correção do ciclo de vida do Boss e auditoria ampliada para
múltiplos clientes e múltiplas sessões.

## Download

- [Baixar RF QOL Setup 2.0.0-beta.5 Beta.exe](https://github.com/Carvalho3009/RFNextInfo/raw/refs/heads/download/rf-qol-2.0.0-beta.5/RF%20QOL%20Setup%202.0.0-beta.5%20Beta.exe)

## Correções desta versão

- a vida e os overlays do Boss somem assim que ele sai da proximidade;
- o dano acumulado fica separado da presença visual e pode continuar se o
  mesmo Boss reaparecer;
- a morte recebida depois do desaparecimento encerra o acumulado do encontro;
- o estado do Boss é isolado por cliente;
- uma nova sessão não reutiliza o estado efêmero da sessão anterior.

## Verificação

- SHA-256: `96CC71222A1539D0F1BCF67D0A00028E1E5872932C04EC8D9D6B150EC04918B8`
- tamanho: `54.082.355 bytes`
- regressão automática: `412 testes aprovados`;
- ensaio do instalador: instalação silenciosa, autoteste e desinstalação
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

