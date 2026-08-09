# Diário de execução — segurança RF QOL 1.0

Branch: `feat/rf-qol-security-1.0`
Worktree: `K:\MCP\_worktrees\rf-qol-security-implementation`
Base: `c85d3b2fd41ed40ff10e8c0ca43f52fe9424b7bd`
Início: 09 ago 2026
Estado: em execução local isolada; sem publicação ou alteração de produção

## Limites autorizados

- Implementação, chaves efêmeras de teste, staging e testes locais: autorizados.
- Uso ou compra de certificado real, chaves privadas reais, produção e release
  pública: não executados nesta branch.
- A Beta 3.0.11 permanece na worktree `rf-next-qol-realtime` e não recebe estas
  alterações.
- Revisão Fable é complementar e não bloqueante; limite/429/timeout é registrado
  como `sem resultado`.

## Linha de base

- Beta remota: `f11f3c1ef9f31ea0b912c7cc1a42390ecdb510be`.
- Tree do produto confirmada: `096b1e07c87d92d181349b66e6f1a79e32015874`.
- Regressão inicial: 182 testes aprovados, 23 ignorados.
- Plano/SPEC/roadmap aprovados no commit local `c85d3b2`.

## Registro por fase

| Data | Fase | Mudança/evidência | Estado |
|---|---|---|---|
| 09 ago 2026 | F0 | Planejamento congelado e worktree de implementação criada. | Concluído |
| 09 ago 2026 | F1 | Emissor Docker localizado em `K:\MCP\projects\rf-licenca`; implementação v2 feita na worktree isolada `rf-licenca-security-r1`. | Concluído local |
| 09 ago 2026 | F1 | Contrato v2, cerimônia de chaves, runbook e vetor público determinístico criados. Privada do vetor descartada. | Concluído local |
| 09 ago 2026 | F2 | Cliente agora aceita somente lease v2 Ed25519 por chave pinada de papel `lease-*`, produto/audience/UUID corretos e janela máxima de 24 h. | Concluído local |
| 09 ago 2026 | F2 | Prefixo da licença nova alterado para `RFQ`; `KRV-*`, lease v1 e estado com chave pública mutável são rejeitados. | Concluído local |
| 09 ago 2026 | F2 | Estados `UNACTIVATED`, `ACTIVE_ONLINE`, `ACTIVE_OFFLINE`, `REVALIDATION_REQUIRED`, `EXPIRED`, `REVOKED` e `INVALID_STATE` implementados. | Concluído local |
| 09 ago 2026 | F2 | Gate aplicado a captura, continuidade, monitor, leitura, importação, consulta, exportação e envio nas interfaces Qt e legada. Perda de autorização encerra captura sem ler os brutos. | Concluído local |
| 09 ago 2026 | F2 | Estado de confiança separado em `%ProgramData%\Karvalho\RF QOL`, protegido por DPAPI machine e ACL Administradores/SYSTEM; preferência/banco/log/captura permanecem separados. | Concluído local |
| 09 ago 2026 | F3 | `rf-next/app/server.py` passou a exigir introspecção ativa v2, `rf-qol`, `rf-qol-windows` e instalação idêntica. | Concluído no site local |
| 09 ago 2026 | F3 | Emissor v2 implementado de forma aditiva: RFQ, chave Ed25519 separada, claims exatos, 6 h/24 h, UUID, produto/audience, rate limit e auditoria pseudonimizada. | Concluído local |
| 09 ago 2026 | F3 | Homologação Docker paralela em `127.0.0.1:8788` passou ativação, cliente, renovação, introspecção, diagnóstico, site e revogação; produção v1 permaneceu saudável. | Concluído staging |
| 09 ago 2026 | F4 | Manifesto v2 fechado, chave distinta `update-*`, SHA-256, tamanho, expiração, sequência e download parcial implementados. | Concluído local |
| 09 ago 2026 | F4 | Authenticode nativo corrigido para ambiente PowerShell 7/Windows PowerShell e reverificado imediatamente antes de abrir o instalador. | Concluído local |
| 09 ago 2026 | F4 | Rollback por cópia de EXE removido. Rollback assinado continua desativado até haver RC anterior e compatibilidade de schema. | Parcial seguro |
| 09 ago 2026 | F5 | Dependências CPython 3.13 fechadas por versão/hash e instaladas offline na própria worktree; SBOM e procedência gerados. | Concluído local |
| 09 ago 2026 | F5 | NSIS 3.12 oficial validado por hash e licença aberta; build portátil e instalador `RF QOL Setup 1.0.0.exe` gerados com procedência ampliada. | Concluído local |
| 09 ago 2026 | F5 | Instalador de ensaio não administrativo instalou, executou o autoteste interno e externo e desinstalou sem deixar executável ou registro. | Concluído local |
| 09 ago 2026 | F5 | Procedência local recebeu assinatura Ed25519 destacada com contexto próprio; dependências do emissor foram fechadas por versão/hash e a imagem-base por digest. | Concluído local |
| 09 ago 2026 | F6 | Ensaio de update aceitou assinatura/hash e bloqueou manifesto adulterado e instalador sem Authenticode. | Concluído local |
| 09 ago 2026 | F6 | Ensaio de cutover migrou cópia somente leitura do banco real com 19 licenças, integridade `ok`, mesma contagem e rollback byte a byte. Porta temporária removida; produção não tocada. | Concluído staging |
| 09 ago 2026 | Marca | Logos anteriores removidos e identidade própria RF QOL criada. | Supersedido pelo owner |
| 09 ago 2026 | Marca | Nome/título/executável/atalhos renomeados; link exato do Discord adicionado com navegador padrão. | Concluído local |
| 09 ago 2026 | Marca | Owner decidiu manter logo e identidade visual Karvalho; assets existentes foram restaurados sem alterar o nome RF QOL. | Concluído local |

## Evidências e comandos de validação

- Regressão rápida CPython 3.11: 186 testes aprovados, 23 ignorados por Qt não
  instalado nesse interpretador.
- Regressão final CPython 3.13 no ambiente virtual fechado: 190 testes
  aprovados, nenhum ignorado, em 98,193 s. Inclui vetor público, assinador
  offline, link exato do Discord e smoke offscreen.
- Self-test do site com catálogos canônicos externos apontados por variáveis:
  `OCR parser OK`, exit code 0.
- Auditoria de papéis confirmou chaves lease/update disjuntas; ambos os gates
  `-pending` permaneceram fechados.
- Varredura de código não encontrou `verify=False`, chave privada PEM ou a
  função de rollback inseguro removida.
- Authenticode nativo validado contra `notepad.exe` assinado pela Microsoft;
  publicador divergente é rejeitado pelos testes.
- Gates de release de lease/update falharam como esperado enquanto as públicas
  têm `-production-pending`.
- O build de desenvolvimento é deliberadamente `NotSigned`; não é release nem
  deve ser distribuído.
- O build recusará release sem NSIS, certificado/timestamp, chave privada
  offline de update e substituição das públicas placeholder.
- Emissor: 14 testes aprovados; configuração Docker de staging validada.
- Integração real em staging: o verificador do cliente recebeu a pública de
  staging somente no teste (`client-verify-ok`); o site aceitou lease v2 válida
  e rejeitou instalação divergente e lease revogada.
- A migração aditiva passou sobre cópia temporária consistente do banco real:
  integridade `ok`, mesma quantidade de licenças e todas classificadas como
  legado. A cópia foi eliminada; a fonte foi aberta somente para leitura.
- A imagem candidata reconstruída com `--require-hashes` ficou saudável em
  `127.0.0.1:8788`; cliente real ativou, atravessou o gate de exportação e a
  introspecção mudou de ativa para inativa após revogação.
- Evidências persistidas fora dos repositórios em `K:\MCP\_staging` cobrem
  instalador NSIS, update e cutover/rollback.
- Fable job 500 revisou o desenho. Foram incorporados chave v2 separada, claims
  exatos, `Retry-After`, UUID, último hop confiável, poda LRU e teto de 512 MiB
  para diagnósticos; a alegação sobre timestamps `Z` foi descartada após
  confronto com o normalizador real do cliente.
- Custo reportado pelo worker Fable: estimativa de USD 4,453115 em assinatura;
  cobrança adicional efetiva permanece `unknown`.

## Identidade visual

- Assets finais: `assets/karvalho-primary-gold.png` e
  `assets/karvalho-symbol-gold.png`.
- O nome oficial do programa e dos executáveis continua RF QOL; somente a
  decisão visual foi revertida.
- Os assets RF QOL gerados anteriormente foram removidos desta branch. A
  alteração é recuperável pelo Git e não afetou a beta em uso.

## Pendências externas reais

1. cerimônia das chaves de produção;
2. certificado Authenticode Karvalho e timestamp RFC 3161;
3. RC anterior assinada para implementar/testar rollback seguro;
4. Windows 10/11 limpos, licença real e teste com até dois clientes;
5. G4 do owner para qualquer publicação ou produção.

## Rollback

O rollback desta etapa é parar/remover o contêiner de staging e descartar as
duas worktrees de implementação. O contêiner oficial v1, a Beta publicada e os
dados reais permanecem intactos.
