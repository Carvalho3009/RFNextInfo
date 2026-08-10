# Diário de execução — segurança RF QOL 1.0

Branch: `feat/rf-qol-security-1.0`
Worktree: `K:\MCP\_worktrees\rf-qol-security-implementation`
Base: `c85d3b2fd41ed40ff10e8c0ca43f52fe9424b7bd`
Início: 09 ago 2026
Estado: cliente em execução local isolada; servidor de licenças v2 promovido,
sem publicação do instalador

## Limites autorizados

- Implementação, chaves efêmeras de teste, staging e testes locais: autorizados.
- A privada real de lease e o servidor de licenças v2 foram promovidos em
  produção por autorização posterior do owner. Release pública do cliente não
  foi executada nesta branch.
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
| 09 ago 2026 | F4 | Rollback por cópia de EXE removido. O rollback assinado permaneceu desativado até haver RC anterior e contrato de compatibilidade. | Supersedido pela implementação posterior |
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
| 09 ago 2026 | Licença | Texto residual da interface corrigido de 72 para o limite offline real de 24 horas; a regra de autorização já aplicava 24 horas. | Concluído local |
| 09 ago 2026 | Chaves | Kit `update-2026-01` v4 fechado sem chave real: duas cópias PEM cifradas, restauração, limpeza de escrita parcial, senha solicitada interativamente, wheelhouse offline e assinatura de update/rollback/procedência. ZIP validado em ambiente novo apenas com seus próprios arquivos; v1/v2/v3 ficaram supersedidos. | Preparado; cerimônia adiada pelo modo manual |
| 09 ago 2026 | F4 | Owner aprovou o manifesto de rollback dedicado. Cliente agora exige alvo idêntico à versão/sequência instalada, compatibilidade assinada com a versão nova, expiração, cache administrativo, segunda reverificação e backup SQLite íntegro antes do UAC. Build exige o bundle completo a partir da segunda release e atesta seu hash. | Concluído local |
| 09 ago 2026 | F4 | Build portátil recompilado lendo versão/sequência do próprio candidato; executável empacotado passou no autoteste. NSIS não estava no PATH daquela sessão, portanto nenhum instalador novo foi emitido. | Supersedido pelo ensaio instalado |
| 09 ago 2026 | Chaves | Owner decidiu pular por enquanto a cerimônia física de `update-2026-01`. Naquele ponto, chave definitiva, publicação e produção continuavam bloqueadas; a decisão posterior pelo modo manual dispensou a chave apenas da 1.0 manual. | Supersedido pela decisão manual |
| 09 ago 2026 | F6 | NSIS 3.12 portátil localizado em `K:\MCP\_tools`. RC1 `1.0.0/1` e RC2 `1.0.1/2` foram construídas em worktrees separadas e instaladas sequencialmente em staging `DEV_SMOKE`: RC1 -> RC2 -> manifesto/compatibilidade/backup -> RC1. Hash final retornou exatamente à RC1 e o banco SQLite foi preservado. | Ensaio instalado local concluído |
| 10 ago 2026 | F6 | Owner decidiu esgotar a validação local e deixar o teste externo para o futuro. Cliente passou 201 testes, emissor passou 15, UI Qt offscreen e executável instalado passaram no smoke, licença oficial/staging permaneceu saudável e a varredura de 22 materiais secretos encontrou zero ocorrências no código e artefatos. | Matriz local concluída |
| 10 ago 2026 | F6 | Owner cancelou definitivamente a validação externa e aceitou a matriz local como escopo final. Windows limpos, observação externa de UAC/SmartScreen, dois clientes externos e revisor independente foram convertidos em riscos residuais aceitos. A decisão não autoriza publicação/produção nem reativar o modo automático sem sua chave definitiva. | G3 encerrado pelo owner |
| 10 ago 2026 | F4/F5 | Owner escolheu instalação manual para a 1.0. Cliente passou a bloquear consulta, download, execução e rollback automáticos; a interface abre o Discord oficial. O build manual gera instalador, procedência e `SHA256SUMS.txt` sem exigir chave de update. | Concluído local |
| 10 ago 2026 | Interface | Owner separou o overlay Boss em vida e DPS, com posições independentes, e removeu os atalhos F1–F4 de envio. Botões de envio e atalhos de captura/monitores foram preservados. | Concluído local |
| 10 ago 2026 | Licença | Owner autorizou a promoção imediata do emissor v2. Backup criptografado e recuperação da chave foram verificados; `lease-2026-01` recebeu ACL restrita em produção; API e backup foram recriados a partir de `d16b770`; gateway liberou somente as rotas v2 aprovadas. `/api/v1` permaneceu compatível, a base continuou íntegra com 19 licenças e o painel exibiu o gerador RFQ. | Produção concluída |
| 10 ago 2026 | Captura | Tráfego do BlueStacks em `HD-Player` usando a mesma porta remota `12020` contaminava a sessão dos dois clientes PC. A ingestão ao vivo passou a aceitar somente fluxos ligados às portas locais detectadas dos processos `ProjectRF.exe`; importações offline continuam inalteradas. | Concluído local |
| 10 ago 2026 | Interface/Captura | A barra lateral foi dividida em PC e Emuladores. Os slots A/B ficaram reservados aos clientes PC e C-G aos cinco BlueStacks, com descoberta independente por processo e as mesmas páginas/módulos em cada categoria. A suíte completa passou com 214 testes e 1 skip ambiental; o computador confirmou descoberta separada de dois ProjectRF e um HD-Player. | Concluído local; cinco BlueStacks físicos não executados |
| 10 ago 2026 | Licença/Conexões | A lease v2 passou a assinar o plano de conexões `2 PC + 1 emulador` ou `2 PC + 5 emuladores`. Emissor, painel, migração aditiva, introspecção, cliente, captura, monitor e interface aplicam o mesmo limite; leases antigas sem o claim são recusadas e licenças RFQ existentes migram para o primeiro plano. | Concluído local; não publicado |
| 10 ago 2026 | Build | O instalador manual 1.0.0 foi reconstruído do commit `0bb7443`, com os planos de conexão, passou regressão, autoteste, procedência, SHA-256 e ensaio isolado de instalação/desinstalação. | Artefato gerado; não instalado nem publicado |
| 10 ago 2026 | Licença/Produção | O emissor `7a1e199` foi promovido após backup e staging. As 20 licenças existentes migraram para 2 PC + 1 emulador; lease descartável 2+5 passou pela superfície pública e pelo cliente antes de ser revogada. | Produção concluída |

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
- Nos ensaios iniciais, os gates de release de lease/update falharam como
  esperado enquanto as públicas tinham `-production-pending`.
- Builds do RF QOL são deliberadamente `NotSigned`. O candidato manual foi
  gerado localmente para validação, mas não foi publicado e não deve ser
  distribuído antes de G4.
- Antes da decisão manual, o build recusava release sem NSIS e chave privada de
  update. No modo vigente, continua exigindo NSIS e confiança de lease, mas
  gera `SHA256SUMS.txt` sem chave ou manifesto de update.
- Fechamento do modo manual em 10 ago 2026: regressão CPython 3.13/Qt passou
  com 205 testes em 109,971 s e um skip ambiental da bandeja. O build de
  release saiu do commit `2613a7e54a5b89f143a062803738e2a7bb4bbd61`, com
  `update_mode=manual`, `dirty=false`, `authenticode=false` e zero artefatos
  de update/rollback automático. O instalador final tem SHA-256
  `4e5c7f6fd1c606821c9331570d62c82efc79aafa379a16704d46908713f88996`,
  idêntico a `SHA256SUMS.txt`.
- O ensaio isolado em
  `K:\MCP\_staging\rf-qol-manual-installer-20260810-r1` compilou o mesmo
  pacote em `DEV_SMOKE`, instalou, comprovou o self-test pós-instalação e
  desinstalou sem deixar o executável. O resultado persistido registra
  `status=passed`, NSIS 3.12 e `NotSigned`.
- Após separar os overlays Boss e remover os atalhos de envio, a regressão
  CPython 3.13/Qt passou com 205 testes em 101,930 s e um skip ambiental da
  bandeja. O novo candidato saiu do commit
  `1d3a083989f3e20b0ebc1bd214c8bde4c5b6b1dd`, em modo manual e tree limpa,
  com SHA-256
  `ced8bdc98150c7c8c68d05be7329aeb400277ca7d18c75f711949dd47668c075`.
  `SHA256SUMS.txt` corresponde ao instalador e o ensaio em
  `K:\MCP\_staging\rf-qol-boss-overlays-20260810-r1` comprovou instalação,
  self-test e desinstalação sem deixar o executável.
- Promoção do emissor v2 em 10 ago 2026: backup
  `rf-licenca-20260810T043200Z.sqlite3.aesgcm` criado e validado; imagem anterior
  preservada como `rf-licenca-api:rollback-pre-v2-20260810`; API saudável;
  SQLite íntegro com 19 licenças; 15 testes aprovados na imagem promovida;
  `/api/v1/public-key`, `/api/v1/updates`, `/api/v2/updates` e
  `/api/v2/introspect` validados pela superfície pública. O painel redireciona
  ao Authentik e, pelo proxy confiável, contém `Gerar chave RFQ`.
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
- Após preparar o fluxo cifrado de update e corrigir o texto de 72 horas, a
  regressão CPython 3.13/Qt passou com 194 testes, nenhum ignorado, em 97,331 s.
- Após implementar o contrato aprovado de rollback, a regressão CPython
  3.13/Qt passou com 201 testes em 111,343 s; um teste de ícone da bandeja foi
  ignorado porque a área de notificação não estava disponível nesse ensaio.
- O ZIP offline passou por verificação de hashes, instalação sem índice de rede
  em ambiente virtual novo, duas restaurações descartáveis, rejeição de senha
  errada e assinatura/verificação de manifesto e procedência. Nenhuma chave
  definitiva foi gerada nesse ensaio.
- Ensaio persistido em
  `K:\MCP\_staging\rf-qol-rollback-contract-20260809-r1` simulou RC2 -> RC1
  com chave descartável: bundle e compatibilidade aceitos, cache sem
  `users-modify`, backup SQLite íntegro/hasheado, adulteração rejeitada e
  reverificação final aprovada. O instalador descartável não foi executado.
- Ensaio instalado persistido em
  `K:\MCP\_staging\rf-qol-installed-rollback-20260809-r1` executou instaladores
  `NotSigned` reais em modo `DEV_SMOKE`: hashes comprovaram RC1 -> RC2 -> RC1,
  manifesto descartável e alvo exato foram aceitos, backup SQLite passou em
  integridade e o dado sentinela foi preservado. Registro/UAC, máquinas limpas
  e chave definitiva não fizeram parte desse ensaio.
- Fechamento local em 10 ago 2026: cliente passou 201 testes em 101,622 s
  (`1` skip ambiental da bandeja), emissor passou 15 testes, UI Qt 6.10.1
  offscreen abriu como `RF QOL — 1.0.0`, executável instalado passou no
  `--self-test`, os contêineres de licença 8787/8788 responderam `ok` e ficaram
  saudáveis. A varredura binária comparou 22 materiais secretos reais e
  descartáveis com cliente, emissor, portátil e instalação de ensaio: zero
  ocorrências; o portátil também ficou sem PCAP, banco ou diretório de runtime.
  Evidência: `local-readiness-result.json` no staging do ensaio instalado.
- Reprodução real do isolamento de clientes: dois processos
  `ProjectRF-Win64-Shipping` estavam conectados pelas portas locais `21530` e
  `21531`, enquanto `HD-Player` usava `57003`, todos contra `12020`. O segmento
  real que identificava `Xonz` como Cliente A continha 1.202 eventos; a nova
  ingestão manteve 1.196 eventos dos clientes PC, excluiu os 6 do fluxo do
  BlueStacks e deixou zero evento de `57003` na base temporária.
- Após o isolamento do BlueStacks, a suíte fechada CPython 3.13/Qt passou com
  209 testes em 224,223 s (`1` skip ambiental da bandeja); o self-test do
  decoder também retornou `ok`.
- Após criar as categorias PC e Emuladores, a suíte fechada CPython 3.13/Qt
  passou com 214 testes em 277,251 s (`1` skip ambiental da bandeja). Os testes
  provaram slots A/B exclusivos para PC, C-G para até cinco BlueStacks,
  rejeição da sexta instância e persistência do Emulador 5 como `client:g`.
  Uma inspeção somente leitura do computador encontrou simultaneamente dois
  processos ProjectRF e um `HD-Player`, cada família com suas portas locais;
  não foi iniciada captura adicional. O cenário físico com cinco BlueStacks
  permanece não executado e não é apresentado como validado.
- Após adicionar os planos de conexão, o emissor isolado passou 15 testes. No
  cliente, a suíte fechada CPython 3.13/Qt passou com 217 testes em 141,592 s e
  um skip ambiental da bandeja. Os testes comprovam os dois planos, rejeição de
  lease antiga, bloqueio do segundo emulador no plano menor antes de iniciar
  captura/monitor, recusa de excesso aberto depois sem parar a captura
  autorizada e slots C-G visíveis, com D-G desabilitados.
- Build manual dos planos de conexão: `RF QOL Setup 1.0.0.exe`, 40.103.107
  bytes, SHA-256
  `8c3852566b81f8e6830d7221ed3f5cff137c5ca822263a6bb93c911d7b6bec85`.
  A procedência registra commit `0bb74435f03fbacb7580bf3ec54c5bcf14c6d00f`,
  `dirty=false`, `update_mode=manual`, `release=true` e o mesmo hash. O build
  passou 217 testes em 143,209 s; o ensaio `DEV_SMOKE` instalou, executou o
  autoteste e desinstalou sem deixar o executável. Ambos permanecem
  deliberadamente `NotSigned` por decisão do owner.
- Revisão Claude Fable solicitada pelo owner: job crítico `504` e tentativa
  direta na conversa `45` falharam antes da inferência porque a sessão OAuth
  do Claude expirou e não pôde ser renovada. Foram processados zero tokens;
  resultado registrado como `sem resultado`, sem substituir por outro modelo
  e sem alterar ou promover a chave. Custo da assinatura: `unknown`.
- Após a indisponibilidade do Fable, o owner decidiu prosseguir sem esse
  parecer automatizado. Testemunha e backup local foram concluídos depois; as
  decisões posteriores também encerraram a validação externa e adiaram a chave
  de update ao escolher instalação manual. G4 permanece separado.
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

## Riscos residuais aceitos e gates restantes

1. `update-2026-01` fica adiada e só será necessária se o modo automático for
   reativado; cópia externa/off-site do backup de lease segue recomendada;
2. não serão executados: Windows 10/11 limpos, observação externa de
   UAC/SmartScreen, teste externo com dois clientes e revisão independente; o
   owner aceitou expressamente esse risco residual em 10 ago 2026;
3. G4 do owner continua obrigatório para qualquer publicação ou produção.

## Rollback

O rollback desta etapa é parar/remover o contêiner de staging e descartar as
duas worktrees de implementação. O contêiner oficial v1, a Beta publicada e os
dados reais permanecem intactos.
