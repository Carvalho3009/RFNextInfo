# Plano de segurança — RF QOL 1.0

Status: planejado, aguardando aprovação do owner para implementação.

Baseline verificada em 09/08/2026:

- produto: RF NEXT QOL 3.0.11 beta;
- commit publicado da branch `beta`: `f11f3c1ef9f31ea0b912c7cc1a42390ecdb510be`;
- commit do monorepo usado no planejamento: `3857f8a5302e0537ddca66c2b044955f498549d9`;
- tree publicada e subtree local: `096b1e07c87d92d181349b66e6f1a79e32015874`;
- regressão inicial: 182 testes aprovados e 23 ignorados por dependência de ambiente.

Este documento planeja a segurança. Ele não autoriza geração de chaves,
alteração do servidor, build, assinatura, instalador, publicação ou deploy.

## Resultado pretendido

Transformar a base 3.0.11 numa instalação nova do RF QOL 1.0 com:

- licenças novas e incompatíveis com as licenças antigas;
- no máximo 24 horas de tolerância offline;
- captura, leitura/processamento, monitores, envio e exportação bloqueados sem
  licença válida;
- arquivos existentes preservados mesmo quando o aplicativo estiver restrito;
- licença e atualização com âncoras de confiança distintas e imutáveis;
- atualização explícita, verificável e sem execução de código gravável por
  usuário;
- executável e instalador assinados pelo publicador Karvalho;
- captura passiva por Pktmon, sem injeção, hooks invasivos, UPX, ofuscação ou
  manipulação do Defender;
- ausência de `0x0101`, token, ticket ou credencial em banco, arquivos, IPC,
  diagnóstico e logs.

## Decisões já aprovadas

- Nome final: `RF QOL`.
- A 1.0 será instalação limpa, com novo `installation_id` e licenças novas.
- Não haverá migração de licença da linha RF NEXT QOL.
- Domínio, suporte, publicador e certificado continuam Karvalho.
- O domínio de licença continua `rflicenca.karvalho.dev.br`.
- A tolerância offline será de 24 horas.
- Sem licença válida não haverá exportação.
- O programa terá link de suporte para
  `https://discord.gg/D3hhdMgkj`, aberto no navegador padrão somente após
  ação do usuário.
- O rollback continua sendo um requisito, mas será feito por instalador
  assinado, nunca por cópia executável numa pasta gravável pelo usuário.

## Evidência encontrada na 3.0.11

### Controles que já existem e devem permanecer

- Lease Ed25519 com `installation_id`, `next_check_at` e `valid_until`.
- Estado local protegido por DPAPI e cópia de recuperação.
- Manifesto de atualização assinado, SHA-256 e confirmação do usuário.
- Logs rotativos com remoção de licença, token, e-mail, IP, UUID e usuário.
- Diagnóstico sanitizado e enviado somente após consentimento.
- Upload do site com introspecção de lease e idempotência.
- Pktmon nativo e ausência intencional de injeção, hooks, UPX e bypass.

### Lacunas críticas

| ID | Lacuna confirmada | Impacto | Tratamento planejado |
|---|---|---|---|
| R-01 | A chave pública da licença é obtida do mesmo servidor durante a ativação e salva como estado mutável. | Um servidor ou resposta comprometida pode introduzir uma chave atacante. | Fixar a chave pública de lease no binário; nenhuma chave recebida da rede participa de verificação. |
| R-02 | A mesma chave mutável também autentica o manifesto de update. | Comprometimento da licença pode virar execução remota de código. | Chave Ed25519 exclusiva de update, pública pinada no binário e privada mantida offline. |
| R-03 | O rollback abre `updates/rollback/RFNextInfo.exe`, dentro de uma árvore `users-modify`. | Substituição local do executável e possível execução elevada. | Remover execução de binário copiado; usar instalador anterior assinado em staging admin-only e reverificá-lo. |
| R-04 | A política atual permite 72 horas offline e orienta exportar após o vencimento. | Contraria a decisão do owner. | Lease v2 com teto de 24 horas imposto também pelo cliente e autorização central para exportação. |
| R-05 | O motor de exportação não exige licença válida antes de gerar JSON/CSV. | Desabilitar apenas botões não impõe a regra. | Gate no motor compartilhado, cobrindo exportação manual, automática, envio e interface legada. |
| R-06 | Executável e instalador não têm Authenticode. | Origem do publicador não é verificável pelo Windows. | Authenticode SHA-256 com timestamp RFC 3161 em ambos. |
| R-07 | Dependências usam intervalos de versão e não há procedência de build registrada. | Build futuro pode incorporar dependências diferentes sem evidência. | Lock com hashes, SBOM, scan de segredos e registro de commit, ferramentas e hashes. |
| R-08 | O emissor de licença não está neste snapshot. | Cliente e site não conseguem adotar lease v2 isoladamente. | Localizar e versionar a alteração do emissor antes de implementar o cliente. |

## Modelo de ameaça

O RF QOL 1.0 deve resistir a:

- alteração do feed ou dos assets de update;
- resposta de licença forjada ou chave pública substituída na rede;
- replay de lease antigo ou de outro produto/instalação;
- downgrade não autorizado;
- adulteração por usuário padrão em diretórios graváveis;
- vazamento acidental de dados sensíveis por logs, banco ou diagnóstico;
- falha ou indisponibilidade temporária do servidor de licença.

Ficam fora do escopo:

- administrador local malicioso, kernel comprometido ou malware com privilégio
  equivalente ao aplicativo;
- impedir cópia manual dos arquivos que pertencem ao usuário;
- ocultação, anti-debug, DRM invasivo ou competição com o anti-cheat;
- TLS pinning. O certificado HTTPS padrão continua obrigatório, mas as
  assinaturas Ed25519 são as âncoras do conteúdo.

O bloqueio local de captura/processamento/exportação é uma regra de produto e
é contornável por um administrador que modifique o binário. O envio ao site é
também imposto no servidor e oferece a garantia mais forte.

## Arquitetura alvo

```text
chave privada de lease (online, servidor)
  -> lease v2 assinada
  -> chave pública de lease pinada no RF QOL

chave privada de update (offline, cerimônia de release)
  -> manifesto v2 assinado
  -> chave pública de update pinada no RF QOL
  -> SHA-256 + tamanho + Authenticode do instalador

servidor/site
  -> introspecção v2
  -> valida product/audience/installation/status/valid_until
```

As chaves têm papéis imutáveis. A chave de lease nunca valida update e a chave
de update nunca valida lease. A chave privada de update não fica no servidor de
licença nem no repositório.

## Fluxo de licença

1. A instalação nova cria `installation_id` aleatório.
2. A chave de acesso nova é enviada apenas à ativação e não é persistida.
3. O servidor emite lease v2 para `rf-qol-windows`.
4. O cliente valida assinatura, issuer, product, audience, instalação e tempo.
5. O cliente tenta renovar ao iniciar e segundo `next_check_at`.
6. Falha de rede mantém as funções licenciadas somente até `valid_until`.
7. `valid_until` nunca pode exceder 24 horas desde a última validação online,
   mesmo que o servidor emita prazo maior por erro.
8. Resposta explícita de revogação/expiração descarta a lease imediatamente.
9. Após o prazo, somente ativação, renovação, suporte, Discord, diagnóstico
   local sanitizado e atualização do programa permanecem disponíveis.
10. Nenhum arquivo do usuário é apagado, alterado ou criptografado pelo
    vencimento da licença.

## Fluxo de atualização

1. O feed é tratado apenas como índice não confiável.
2. O cliente baixa o manifesto v2 e valida a assinatura com a chave de update
   pinada.
3. O manifesto precisa corresponder ao produto, canal, arquitetura, versão e
   sequência esperados.
4. O instalador é baixado para staging admin-only.
5. Tamanho, SHA-256 e Authenticode do publicador esperado são verificados.
6. O usuário vê versão e changelog e confirma a instalação.
7. As verificações são repetidas imediatamente antes da execução.
8. O aplicativo fecha captura e banco de forma consistente.
9. O instalador executa com UAC e registra resultado/self-test.
10. Rollback usa o instalador anterior assinado e só é permitido quando a
    compatibilidade de dados estiver declarada no manifesto.

Nenhum executável é iniciado a partir de pasta `users-modify`. Atualizações de
segurança continuam disponíveis quando a licença está ausente ou vencida.

## Dados e permissões

- Binário, `_internal`, instaladores em staging, estado anti-downgrade e estado
  protegido de licença: graváveis apenas por Administradores/SYSTEM.
- Preferências, banco, cache, logs e capturas: podem ser graváveis pelo usuário
  conforme a função.
- Diretórios graváveis pelo usuário nunca são fonte de executável, DLL,
  plugin, script ou chave de confiança carregados pelo aplicativo.
- DPAPI `LOCAL_MACHINE` só pode proteger o estado de instalação quando o ACL do
  arquivo limitar leitura/escrita a Administradores/SYSTEM. DPAPI não substitui
  ACL nem assinatura.

## Cadeia de fornecimento e release

- Dependências resolvidas e registradas com versões e hashes.
- Build em ambiente limpo e rastreável.
- SBOM por release.
- Scan de segredos e de artefatos proibidos.
- Registro de commit, versão do Python, PyInstaller, dependências, SHA-256 do
  executável, instalador e manifesto.
- Authenticode SHA-256 com timestamp RFC 3161.
- Atestação de procedência do GitHub quando o build ocorrer no Actions; para
  build local, `release-provenance.json` assinado faz parte do gate.
- Nenhuma chave privada, PFX, senha ou token entra no repositório ou no
  pacote do cliente.

## Referências oficiais

- Microsoft, DPAPI `CryptProtectData`:
  https://learn.microsoft.com/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata
- Microsoft, timestamp Authenticode:
  https://learn.microsoft.com/windows/win32/seccrypto/time-stamping-authenticode-signatures
- GitHub, artifact attestations:
  https://docs.github.com/actions/concepts/security/artifact-attestations
- NIST SP 800-218, SSDF:
  https://csrc.nist.gov/projects/ssdf

## Regra de revisão paralela

A revisão do Fable é complementar. Limite de sessão, HTTP 429, timeout ou
indisponibilidade devem ser registrados como `sem resultado`, nunca como
aprovação ou reprovação. O planejamento e a implementação continuam com a
evidência local, as fontes oficiais, os testes previstos e os gates do owner.

## Próximo gate

O owner aprovou em 09 ago 2026 a implementação máxima em ambiente isolado, com
execução autônoma e documentação para revisão posterior. Isso autoriza código,
chaves de desenvolvimento, staging e testes locais; não autoriza publicação,
produção, compra ou uso de certificado/chaves reais não disponíveis.
