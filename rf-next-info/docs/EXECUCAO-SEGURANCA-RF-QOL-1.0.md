# Diário de execução — segurança RF QOL 1.0

Branch: `feat/rf-qol-security-1.0`
Worktree: `K:\MCP\_worktrees\rf-qol-security-implementation`
Base: `c85d3b2fd41ed40ff10e8c0ca43f52fe9424b7bd`
Início: 09 ago 2026
Estado: em execução local isolada; sem publicação ou alteração de produção

## Limites autorizados

- Implementação, chaves efêmeras de teste, staging e testes locais: autorizados.
- Chaves privadas reais, produção e release pública: não executados nesta branch.
- O owner decidiu que o RF QOL 1.0 não terá certificado Authenticode; compra,
  uso e timestamp de certificado foram removidos do escopo.
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
| 09 ago 2026 | F4 | Authenticode nativo corrigido e testado antes da decisão posterior do owner de não usar certificado. | Supersedido |
| 09 ago 2026 | F4 | Rollback por cópia de EXE removido. Rollback assinado continua desativado até haver RC anterior e compatibilidade de schema. | Parcial seguro |
| 09 ago 2026 | F5 | Dependências CPython 3.13 fechadas por versão/hash e instaladas offline na própria worktree; SBOM e procedência gerados. | Concluído local |
| 09 ago 2026 | F5 | NSIS 3.12 oficial validado por hash e licença aberta; build portátil e instalador `RF QOL Setup 1.0.0.exe` gerados com procedência ampliada. | Concluído local |
| 09 ago 2026 | F5 | Instalador de ensaio não administrativo instalou, executou o autoteste interno e externo e desinstalou sem deixar executável ou registro. | Concluído local |
| 09 ago 2026 | F5 | Procedência local recebeu assinatura Ed25519 destacada com contexto próprio; dependências do emissor foram fechadas por versão/hash e a imagem-base por digest. | Concluído local |
| 09 ago 2026 | F6 | Ensaio original bloqueou instalador sem Authenticode; esse critério foi supersedido pela decisão posterior do owner. | Supersedido |
| 09 ago 2026 | F6 | Ensaio de cutover migrou cópia somente leitura do banco real com 19 licenças, integridade `ok`, mesma contagem e rollback byte a byte. Porta temporária removida; produção não tocada. | Concluído staging |
| 09 ago 2026 | Marca | Logos anteriores removidos e identidade própria RF QOL criada. | Supersedido pelo owner |
| 09 ago 2026 | Marca | Nome/título/executável/atalhos renomeados; link exato do Discord adicionado com navegador padrão. | Concluído local |
| 09 ago 2026 | Marca | Owner decidiu manter logo e identidade visual Karvalho; assets existentes foram restaurados sem alterar o nome RF QOL. | Concluído local |
| 09 ago 2026 | Segurança | Owner decidiu não usar certificado Authenticode. Verificador, build e gates passaram a exigir manifesto/procedência Ed25519, tamanho e SHA-256, registrando `authenticode=false`. | Concluído local |
| 09 ago 2026 | Licença | Permissões `base`, `monitor-pve`, `monitor-pvp` e `monitor-boss` foram adicionadas à lease assinada e ao painel do emissor. PvE/PvP ficam visíveis e bloqueados sem módulo; Boss fica invisível. Gates cobrem atalhos, overlays e motor compartilhado. | Concluído local |
| 09 ago 2026 | Chaves | Par definitivo de lease `lease-2026-01` gerado sob ACL restrita, pública pinada no cliente e autoteste aprovado. Privada não promovida à produção; testemunha e backup de recuperação continuam pendentes. Chave de update não foi gerada neste computador online. | Parcial seguro |
| 09 ago 2026 | Chaves | Emissor Docker efêmero 8789 assinou Base+Boss com `lease-2026-01`; cliente com a pública definitiva aceitou Boss, negou PvP e a licença de ensaio foi revogada. Contêiner efêmero removido; 8787/8788 permaneceram saudáveis. | Concluído staging |
| 09 ago 2026 | Chaves | Carlos confirmou como revisor humano `lease-2026-01`, a pública, o SHA-256, a ACL e que a privada permanece fora da produção. Backup de recuperação continua pendente e bloqueia promoção. | Revisão concluída |
| 09 ago 2026 | Chaves | Backup local AES-256-GCM criado em `D:` com chave de recuperação separada em `E:`; origem permanece em `K:`. ACL restrita, restauração exata aprovada, chave errada rejeitada e nenhum segredo encontrado nos arquivos rastreados dos dois repositórios. Cópia off-site segue recomendada. | Backup local validado |

## Evidências e comandos de validação

- Regressão rápida CPython 3.11: 186 testes aprovados, 23 ignorados por Qt não
  instalado nesse interpretador.
- Regressão final CPython 3.13 no ambiente virtual fechado: 190 testes
  aprovados, nenhum ignorado, em 98,193 s. Inclui vetor público, assinador
  offline, link exato do Discord e smoke offscreen.
- Após remover Authenticode por decisão do owner, a regressão CPython 3.13
  passou com 189 testes, nenhum ignorado, em 88,108 s. A redução de um teste
  corresponde à exclusão do verificador Authenticode; a cadeia
  Ed25519/tamanho/SHA-256 e a declaração `authenticode=false` permanecem
  cobertas.
- Self-test do site com catálogos canônicos externos apontados por variáveis:
  `OCR parser OK`, exit code 0.
- Auditoria de papéis confirmou chaves lease/update disjuntas; ambos os gates
  `-pending` permaneceram fechados.
- Varredura de código não encontrou `verify=False`, chave privada PEM ou a
  função de rollback inseguro removida.
- A validação Authenticode anterior permanece apenas como evidência histórica;
  o código correspondente foi removido após a decisão do owner.
- Gates de release de lease/update falharam como esperado enquanto as públicas
  têm `-production-pending`.
- Builds do RF QOL são deliberadamente `NotSigned`; o build de desenvolvimento
  atual não é release e não deve ser distribuído.
- O build recusará release sem NSIS, chave privada offline de update e
  substituição das públicas placeholder.
- Emissor: 14 testes aprovados; configuração Docker de staging validada.
- Emissor após módulos: 15 testes aprovados. Cliente: 190 testes aprovados,
  nenhum ignorado, em 97,024 s no ambiente CPython 3.13/Qt fechado; vetor
  público e smoke offscreen incluídos.
- Homologação 8788 confirmou licença `base+monitor-pvp`, introspecção dos
  módulos, mudança para `base+monitor-boss` na renovação e revogação final da
  licença descartável. Produção 8787 permaneceu saudável e não foi alterada.
- Após pinar `lease-2026-01`, a regressão CPython 3.13/Qt passou com 191
  testes, nenhum ignorado, em 88,464 s. O teste adicional confirma que o gate
  de lease está aberto e o gate independente de update permanece fechado.
- Revisão Claude Fable solicitada pelo owner: job crítico `504` e tentativa
  direta na conversa `45` falharam antes da inferência porque a sessão OAuth
  do Claude expirou e não pôde ser renovada. Foram processados zero tokens;
  resultado registrado como `sem resultado`, sem substituir por outro modelo
  e sem alterar ou promover a chave. Custo da assinatura: `unknown`.
- Após a indisponibilidade do Fable, o owner decidiu prosseguir sem esse
  parecer automatizado. A dispensa se limita ao Fable: testemunha humana,
  backup de recuperação, chave offline de update, testes RC e G4 permanecem
  como gates obrigatórios antes de promoção ou publicação. Testemunha e backup
  local foram concluídos depois; os demais gates continuam abertos.
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
- O ensaio sem certificado em
  `K:\MCP\_staging\rf-qol-no-authenticode-20260809-r2` confirmou
  `authenticode_status=NotSigned`, instalação, autoteste e desinstalação, sem
  deixar o executável no destino.
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

1. cópia externa/off-site recomendada do backup de lease e cerimônia offline
   da chave de update;
2. RC anterior coberta por manifesto Ed25519 para implementar/testar rollback seguro;
3. Windows 10/11 limpos, licença real e teste com até dois clientes;
4. G4 do owner para qualquer publicação ou produção.

## Rollback

O rollback desta etapa é parar/remover o contêiner de staging e descartar as
duas worktrees de implementação. O contêiner oficial v1, a Beta publicada e os
dados reais permanecem intactos.
