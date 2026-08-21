# RF QOL 2.0.0-beta.4

Beta pública com a correção do status de Farm validada em capturas reais.

## Download

- [Baixar RF QOL Setup 2.0.0-beta.4 Beta.exe](https://github.com/Carvalho3009/RFNextInfo/raw/refs/heads/download/rf-qol-2.0.0-beta.4/RF%20QOL%20Setup%202.0.0-beta.4%20Beta.exe)

## Correção desta versão

- corrige a correlação entre o pedido de habilidade do cliente e a resposta do
  servidor no protocolo atual;
- o UID local volta a ser identificado durante o combate;
- dano e abate de monstro nos últimos 30 segundos passam a definir o status
  como `Farm`;
- a correção foi reproduzida nos fluxos reais dos dois clientes ativos.

## Verificação

- SHA-256: `F1043E0DEE759E2909AD6B8CC1056D9D24D69FAD581F542A46950FA5A51785F9`
- tamanho: `54.085.616 bytes`
- regressão automática: `406 testes aprovados`
- ensaio do instalador: instalação silenciosa, autoteste e desinstalação aprovados;
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
