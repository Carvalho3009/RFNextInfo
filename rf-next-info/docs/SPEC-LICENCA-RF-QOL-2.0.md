# RF QOL 2.0 — Política de licença e lease v3

Status: cliente, emissor v3 e consumidor dual do site implementados localmente
em 2026-08-17, com chave isolada e serviço do emissor em staging validados. A
configuração `2.0.0-rc1 (Homologação)` está preparada com estado separado,
chave pública de staging e site remoto bloqueado. A chave definitiva, o
executável, o site de produção e a publicação não foram alterados.

## Decisões do owner

- a versão 2.0 não possui cotas de quantidade de clientes PC, emuladores ou
  clientes externos recebidos pela API;
- a licença continua obrigatória para liberar os módulos contratados;
- a tolerância offline passa de 24 horas para no máximo 7 dias;
- o programa tenta revalidar a licença em toda abertura;
- abrir o programa sem sucesso de rede não renova nem reinicia localmente os 7
  dias;
- não existe mais uma revalidação obrigatória baseada em ciclo de 24 horas;
- as features aprovadas são `base`, `monitor-pve`, `monitor-pvp`,
  `monitor-boss`, `map`, `sessions-lan` e `exp-ranking`;
- a lease v3 usará uma chave Ed25519 exclusiva, separada da chave que assina a
  lease v2.

Essas decisões alteram somente a política da 2.0. A lease v2 e os clientes 1.x
continuam com seus contratos atuais até uma migração ou retirada autorizada em
etapa própria.

## Separação entre cota e autorização

A licença 2.0 autoriza **funcionalidades**, não quantidades de clientes:

- `features` continua sendo a lista assinada de módulos liberados;
- `base` continua obrigatória;
- um módulo só pode iniciar, aparecer como habilitado ou executar uma ação se a
  lease estiver válida e sua feature estiver presente;
- a ausência de cota não libera um módulo que não foi contratado;
- quantidade de clientes não entra em claims, regras do emissor, painel,
  introspecção ou mensagens da interface;
- clientes locais, emuladores e `remote_api` não consomem cota de licença;
- adicionar clientes continua sujeito ao orçamento de RAM, concorrência segura,
  capacidade real da captura e limites técnicos específicos, como as duas vagas
  do Módulo Mapa. Esses limites não são licença nem plano comercial.

Limite de ativações por instalação, vínculo de `installation_id`, situação da
licença, expiração do entitlement e revogação permanecem controles distintos e
não são removidos por esta decisão.

## Por que uma lease v3

A lease v2 exige campos e limites incompatíveis com a nova política:

- `connection_limits` obrigatório;
- `next_check_at` em até 6 horas;
- `valid_until` em até 24 horas.

Alterar o significado desses campos sem mudar a versão quebraria validação
fechada, vetores públicos, clientes 1.x e rollback. A 2.0 deve usar lease v3,
aditiva, enquanto `/api/v2` permanece disponível para as versões anteriores.

## Contrato proposto da lease v3

Endpoints planejados:

- `POST /api/v3/activate` — ativa a licença para uma instalação 2.0;
- `POST /api/v3/validate` — revalida a lease na abertura do programa;
- introspecção v3 para os serviços que recebem dados do RF QOL 2.0.

Claims assinados exatos:

```json
{
  "v": 3,
  "iss": "rflicenca.karvalho.dev.br",
  "product": "rf-qol",
  "aud": "rf-qol-windows",
  "key_id": "lease-v3-...",
  "lease_id": "uuid-ou-id-opaco",
  "license_id": "id-opaco",
  "installation_id": "uuid",
  "issued_at": "UTC",
  "valid_until": "UTC",
  "entitlement_expires_at": "UTC",
  "features": ["base", "monitor-pve", "monitor-pvp"]
}
```

Campos removidos em relação à v2:

- `connection_limits`;
- `next_check_at`.

Invariantes:

- `issued_at <= valid_until <= entitlement_expires_at`;
- `valid_until - issued_at <= 7 dias`;
- nova validação online bem-sucedida gera outro `lease_id` e nova janela;
- o cliente nunca amplia `valid_until` por cálculo local;
- datas usam UTC com fuso e continuam protegidas contra recuo de relógio;
- assinatura, produto, audience, instalação, chave pinada e ordem canônica de
  `features` continuam validados de forma fechada;
- claims desconhecidos, ausentes ou duplicados invalidam a lease.

O `valid_until` real é o menor valor entre 7 dias após `issued_at` e a expiração
do entitlement. Uma licença que termina amanhã não recebe sete dias adicionais.

## Fluxo em toda abertura

1. carregar e verificar o comprovante v3 protegido localmente;
2. verificar assinatura, instalação, relógio, entitlement e `valid_until`;
3. iniciar uma única tentativa de `POST /api/v3/validate` naquela abertura;
4. se houver comprovante local ainda válido, a interface pode abrir os módulos
   já autorizados enquanto a tentativa ocorre em segundo plano;
5. se não houver comprovante válido, os módulos permanecem bloqueados até uma
   resposta online válida;
6. sucesso substitui atomicamente o comprovante e reinicia a janela assinada de
   até 7 dias;
7. `401/403` explícito limpa o comprovante ativo e bloqueia os módulos
   imediatamente;
8. timeout, falta de internet ou `5xx` preserva o comprovante somente até o
   `valid_until` já assinado;
9. resposta inválida nunca vira autorização, mas um comprovante anterior ainda
   válido pode continuar até seu próprio vencimento;
10. durante a mesma execução não existe consulta periódica obrigatória de 24
    horas.

A tentativa é única por inicialização do processo, com timeout limitado. Fechar
e abrir repetidamente gera novas tentativas conforme decidido pelo owner; o
emissor mantém rate limit e resposta `429`, sem transformar `429` em revogação.

## Programa mantido aberto

O fim da validação de 24 horas não permite usar uma lease vencida:

- `require()` e os gates dos módulos continuam verificando `valid_until`;
- a interface agenda uma verificação local para o instante de expiração;
- ao chegar a `valid_until`, captura e módulos protegidos são encerrados de
  forma segura e ficam bloqueados;
- não há renovação automática de rede durante a execução nesta primeira
  política;
- o usuário pode fechar e abrir o programa para disparar a nova tentativa;
- um botão manual **Tentar validar agora** pode repetir a mesma operação sem
  alterar a janela local por conta própria.

## Estados e mensagens

- `ACTIVE_ONLINE` — revalidação desta abertura concluída;
- `ACTIVE_OFFLINE` — servidor indisponível, comprovante ainda dentro dos 7 dias;
- `REVALIDATION_REQUIRED` — recuo de relógio ou condição que exige servidor;
- `EXPIRED` — `valid_until` terminou;
- `REVOKED` — servidor recusou explicitamente;
- `UNACTIVATED` e `INVALID_STATE` permanecem.

Exibição recomendada:

- **Licença validada nesta abertura**;
- **Sem conexão. Módulos disponíveis offline até <data/hora>**;
- **Tentando revalidar a licença…**;
- **Prazo offline de 7 dias encerrado. Conecte para validar**;
- lista de módulos liberados;
- nenhuma linha de quantidade de PC, emuladores ou clientes externos;
- nenhuma mensagem **Próxima validação em 24 horas**.

## Features aprovadas

O gate continua em todas as superfícies: botão, atalho, aba, overlay, worker,
API interna e operação direta. Esconder ou desabilitar um botão não substitui a
validação no núcleo.

Ordem canônica aprovada para a lease v3:

- `base`;
- `monitor-pve`;
- `monitor-pvp`;
- `monitor-boss`;
- `map`;
- `sessions-lan`;
- `exp-ranking`.

`base` é obrigatória e sempre aparece primeiro. As outras features são opcionais
e só podem aparecer nessa ordem relativa, sem duplicação ou chave desconhecida.

### Mapa funcional

| Feature | Funcionalidades incluídas |
|---|---|
| `base` | núcleo, licença, captura passiva, coleção de clientes, sessões/subsessões/histórico, EXP e recursos locais, inventário, Mercado, Codex, Coleção, Memory Chips, projeção de leilão compatível, status básico, motor de alertas/sons, saúde, configurações e APIs básicas `health`/`status` |
| `monitor-pve` | Monitor PvE, alvo atual, Banco PvE, HP/localizações de mobs, sincronização PvE, contexto de mobs da subsessão e regras/alertas derivados de PvE |
| `monitor-pvp` | Monitor PvP, alvo/lista/overlays, Banco PvP compatível e congelado na 2.0, relações governadas e regras/alertas derivados de PvP |
| `monitor-boss` | Monitor Boss, vida, DPS, rankings de dano e overlays/regras derivados de Boss |
| `map` | mapa, coordenadas, jogadores próximos, API `/map`, contexto espacial e preenchimento de mapa/spot na subsessão |
| `sessions-lan` | servidor/cliente LAN, pareamento, consulta de sessões, **Externo via API** e o resumo sanitizado aprovado de EXP, nível, tempo, recursos e combate |
| `exp-ranking` | captura passiva, integridade, aba e API do Top 100 oficial de EXP do servidor |

### Funcionalidades compartilhadas

- status, alertas e sons pertencem à `base`, mas um sinal de PvE, PvP, Boss ou
  Mapa só existe quando a feature de origem estiver liberada;
- APIs básicas `health` e `status` usam `base`; `/map` usa `map`; rotas LAN usam
  `sessions-lan`; ranking usa `exp-ranking`; envio/consulta do Banco PvE usa
  `monitor-pve`;
- automação de subsessão compõe features: mapa exige `map`, mobs exigem
  `monitor-pve`, e o spot que depende dos dois só é preenchido quando ambos
  estiverem ativos;
- `sessions-lan` inclui o resumo remoto mínimo de combate definido no contrato
  LAN, mas não libera as telas, overlays ou detalhes dos monitores PvE/PvP/Boss;
- Banco PvP e projeção de leilão mantêm apenas a compatibilidade prevista para a
  2.0; suas evoluções permanecem no backlog 2.1;
- memória, checkpoints, segurança, atualizador e rollback são infraestrutura,
  não features comerciais separadas.

## Migração v2 para v3

- `/api/v2` e o verificador v2 permanecem para clientes 1.x;
- a 2.0 tenta obter uma lease v3 em toda abertura;
- uma lease v2 já armazenada pode ser aceita pela 2.0 somente até seu
  `valid_until` original de no máximo 24 horas;
- lease v2 nunca é reinterpretada nem estendida localmente para 7 dias;
- após receber e persistir uma v3, a 2.0 não volta automaticamente para a v2;
- o estado v3 deve ser versionado/aditivo para permitir rollback do executável
  sem corromper o estado v2;
- emissor e site adotam v3 de forma aditiva; remover v2 exige outro gate;
- colunas antigas de plano de conexão podem permanecer no banco legado, mas não
  participam da emissão v3 e não devem aparecer como cota da 2.0.

## Segurança e impacto da janela de 7 dias

A janela maior melhora disponibilidade offline, mas amplia para até sete dias o
tempo em que uma revogação feita no servidor pode não ser percebida por um
computador sem conexão. Essa consequência é aceita pela política escolhida e
deve aparecer no gate de segurança/release.

Permanecem obrigatórios:

- chave pública pinada;
- privada somente no emissor;
- DPAPI e ACL para estado local;
- guarda contra recuo de relógio;
- comparação fechada de claims;
- revogação imediata quando o servidor responder;
- auditoria sanitizada sem chave, lease completa ou dados do jogo;
- rate limit, timeout e proteção contra replay no emissor.

Decisão do owner em 2026-08-17: a v3 estreia uma chave Ed25519 exclusiva, com
`key_id` próprio. A chave v2 permanece destinada aos clientes 1.x e não será
substituída por esta decisão. Durante a migração, o cliente 2.0 poderá confiar
nas duas chaves para validar o estado legado e o novo contrato, mas o emissor v3
assinará somente com a chave v3.

Essa separação reduz o impacto de comprometimento e permite revogar ou retirar
a v3 sem interromper a emissão v2. Gerar uma chave isolada de staging faz parte
da futura implementação em staging. Gerar, custodiar ou promover a chave
definitiva de produção, realizar cutover ou publicar o cliente continuam gates
externos separados.

## Testes automáticos

A implementação local cobre os contratos abaixo. Os ensaios do executável e o
cutover continuam em gates posteriores:

- claims v3 aceitos sem `connection_limits` e `next_check_at`;
- presença desses campos legados rejeitada na v3;
- limite exato em `issued_at + 7 dias`;
- entitlement menor que 7 dias prevalece;
- tentativa online em toda inicialização, mesmo com lease recente;
- sucesso rotaciona `lease_id` e persiste atomicamente;
- timeout/5xx mantém cache válido, mas nunca estende o prazo;
- `401/403` revoga imediatamente;
- `429` não revoga nem estende a lease;
- expiração durante execução bloqueia todos os módulos;
- cada módulo exige lease ativa e feature correspondente em chamadas diretas;
- a lista completa das sete features é aceita somente na ordem canônica;
- feature desconhecida, duplicada ou fora de ordem invalida a lease;
- sinais, regras, sons e APIs derivados de um módulo não funcionam sem a feature
  de origem;
- `sessions-lan` não libera telas, overlays nem detalhes dos monitores;
- subsessão automática exige `map` para mapa/spot e `monitor-pve` para mobs;
- número de clientes não altera autorização;
- cliente 1.x continua validando v2 e rejeitando v3;
- migração v2 → v3 e rollback não corrompem nenhum estado;
- recuo de relógio continua exigindo revalidação online.

## Gates

Resolvidos pelo owner:

1. sem cotas de clientes na 2.0;
2. módulos continuam condicionados à licença;
3. tolerância offline máxima de 7 dias;
4. tentativa online em toda abertura;
5. sem ciclo obrigatório de revalidação de 24 horas;
6. sete features canônicas e seu mapa funcional aprovados;
7. chave Ed25519 exclusiva para a lease v3, preservando a chave v2.

Pendentes antes da publicação:

1. validar migração/rollback v2 → v3 no executável candidato;
2. autorizar separadamente a geração/custódia da chave definitiva de produção;
3. validar o consumidor dual no staging integrado do site;
4. aprovar mudança de produção, executável e publicação em gates separados.

## Rollback planejado

O rollout é aditivo. Desativar v3 no gateway e voltar o cliente candidato
restaura o fluxo v2 para versões 1.x. Estado v3 fica separado e pode ser
ignorado pelo executável anterior. Nenhuma licença, sessão ou configuração de
módulo é apagada automaticamente. Um rollback não converte uma lease v3 em v2;
o cliente anterior deve obter sua própria v2 pelo emissor legado.
