# SPEC de segurança — RF QOL 1.0

Versão do documento: 1.0-draft  
Baseline: RF NEXT QOL 3.0.11 beta  
Estado: aprovada pelo owner em 09 ago 2026 para implementação local isolada;
publicação permanece não autorizada

Os termos DEVE, NÃO DEVE e SOMENTE indicam requisitos obrigatórios para a
release pública.

## 1. Objetivo e escopo

Esta SPEC define:

- confiança de licença e atualização;
- comportamento online/offline;
- autorização de recursos;
- armazenamento protegido e ACLs;
- update, rollback e anti-downgrade;
- privacidade, logs e diagnósticos;
- cadeia de build, assinatura e critérios de release.

Não altera semântica do decoder, opcodes, Pktmon, cálculo de EXP/loot ou
contratos funcionais do site além da validação de licença.

## 2. Identidade do produto

- `product`: `rf-qol`
- `audience`: `rf-qol-windows`
- nome exibido: `RF QOL`
- executável principal: `RF QOL.exe`
- instalador: `RF QOL Setup 1.0.0.exe`
- versão inicial: `1.0.0`
- issuer de licença: `rflicenca.karvalho.dev.br`
- empresa exibida nos metadados: Karvalho
- assinatura de código do Windows: não utilizada
- suporte Discord: `https://discord.gg/D3hhdMgkj`

O produto e os executáveis usam o nome RF QOL. Por decisão do owner em
09 ago 2026, a identidade visual e o logo permanecem Karvalho, que também
continua nos papéis de domínio, suporte e empresa exibida nos metadados. Em
decisão posterior na mesma data, o owner determinou que o programa não terá
certificado Authenticode. O Windows poderá mostrar `Publicador desconhecido` e
alertas do SmartScreen; isso não deve ser apresentado como falha da cadeia
Ed25519 do produto.

A 1.0 DEVE ser instalação nova. Estado e licenças da linha RF NEXT QOL NÃO
DEVEM ser migrados nem aceitos. Arquivos antigos NÃO DEVEM ser apagados pela
nova instalação.

## 3. Âncoras de confiança

### 3.1 Separação obrigatória

O binário DEVE conter duas chaves públicas Ed25519 distintas:

- chave de lease;
- chave de manifesto/update.

A chave de lease NÃO DEVE validar manifesto. A chave de update NÃO DEVE
validar lease. `key_id` DEVE identificar o papel, por exemplo
`lease-2026-01` e `update-2026-01`.

Nenhuma chave pública recebida da rede, API, arquivo de estado, configuração,
registro ou preferência pode participar da verificação. O endpoint legado
`/api/v1/public-key`, se mantido por compatibilidade, é apenas informativo.

### 3.2 Chaves privadas

- A chave privada de lease pode permanecer online no emissor de licença.
- A chave privada de update DEVE permanecer offline e ser usada somente na
  cerimônia de release.
- As duas chaves privadas NÃO DEVEM compartilhar arquivo, segredo, conta ou
  permissões.
- Nenhuma chave privada pode existir no repositório ou no cliente.

Propriedade exigida: comprometer o servidor de licença NÃO DEVE permitir que o
atacante publique código aceito pelos clientes.

### 3.3 Rotação

Uma nova chave pública só pode ser introduzida por versão assinada pela chave
anterior ainda confiável. Durante a transição, o binário pode conter `current`
e `next`; após a janela aprovada, a chave antiga é removida. Comprometimento da
chave de update exige bloquear o feed e distribuir instalador manual pelo canal
oficial, com hashes publicados por um canal independente.

## 4. Lease v2

### 4.1 Claims obrigatórios

```json
{
  "v": 2,
  "iss": "rflicenca.karvalho.dev.br",
  "product": "rf-qol",
  "aud": "rf-qol-windows",
  "key_id": "lease-AAAA-NN",
  "lease_id": "identificador aleatorio",
  "license_id": "identificador da licenca",
  "installation_id": "uuid aleatorio da instalacao",
  "issued_at": "UTC ISO-8601",
  "next_check_at": "UTC ISO-8601",
  "valid_until": "UTC ISO-8601",
  "entitlement_expires_at": "UTC ISO-8601",
  "features": ["base", "monitor-pve", "monitor-pvp", "monitor-boss"]
}
```

O cliente DEVE rejeitar:

- assinatura inválida;
- `v`, issuer, product ou audience divergente;
- `key_id` desconhecido ou de papel errado;
- `installation_id` diferente;
- datas inválidas, ausentes ou fora de ordem;
- `valid_until` superior a 24 horas após `issued_at`;
- `valid_until` posterior a `entitlement_expires_at`;
- lease v1 ou licença da linha anterior.
- claim ausente ou extra, módulo desconhecido/duplicado/fora da ordem canônica,
  ou licença sem o módulo obrigatório `base`.

### 4.2 Renovação e tolerância offline

- O cliente tenta validar ao iniciar quando houver rede.
- `next_check_at` NÃO DEVE ser posterior a seis horas após `issued_at`.
- Falha de rede permite uso SOMENTE até o `valid_until` assinado.
- O teto local é 24 horas após a última validação online bem-sucedida.
- Resposta online `revoked`, `expired`, `disabled` ou equivalente bloqueia
  imediatamente e remove a lease ativa do estado.
- Não haverá CRL local nem canal adicional de revogação na 1.0; o TTL máximo de
  24 horas é o limite de revogação offline.

### 4.3 Relógio

O estado protegido DEVE registrar o maior horário de servidor aceito. Se o
relógio local recuar mais de cinco minutos em relação a esse valor, o cliente
entra em `REVALIDATION_REQUIRED` até validar online. Tempo monotônico deve ser
usado dentro do mesmo processo.

Esses controles são best-effort contra adulteração local; administrador local
malicioso permanece fora do modelo de ameaça.

## 5. Máquina de estados e autorização

Estados normativos:

- `UNACTIVATED`
- `ACTIVE_ONLINE`
- `ACTIVE_OFFLINE`
- `REVALIDATION_REQUIRED`
- `EXPIRED`
- `REVOKED`
- `INVALID_STATE`

Somente `ACTIVE_ONLINE` e `ACTIVE_OFFLINE` autorizam funções licenciadas.

| Capacidade | Licença válida | Sem licença válida |
|---|---:|---:|
| Ativar/renovar | Sim | Sim |
| Ver status e suporte | Sim | Sim |
| Abrir Discord no navegador padrão | Sim | Sim |
| Gerar diagnóstico local sanitizado | Sim | Sim |
| Verificar/instalar atualização assinada | Sim | Sim |
| Iniciar ou continuar Pktmon | Sim | Não |
| Monitor PvE em RAM | Somente com `monitor-pve` | Não |
| Monitor PvP em RAM | Somente com `monitor-pvp` | Não |
| Monitor Boss em RAM | Somente com `monitor-boss` | Não |
| Importar, ler ou processar nova captura | Sim | Não |
| Consultar dados capturados pela interface | Sim | Não |
| Exportar JSON/CSV/diagnóstico de sessão | Sim | Não |
| Autoexportar ao parar | Sim | Não |
| Enviar ao site | Sim | Não |

`base` autoriza captura, ingestão, leitura, exportação e envio. Sem a permissão
correspondente, as abas Monitor PvE e Monitor PvP DEVEM permanecer visíveis,
desabilitadas e inacessíveis; a aba Boss DEVE ficar invisível. Atalhos,
overlays e chamadas diretas ao motor DEVEM aplicar o mesmo gate, sem depender
da visibilidade do botão.

Alterações de módulos entram na próxima renovação online, prevista em até seis
horas. Uma lease já emitida pode conservar os módulos anteriores somente até
`valid_until`, limitado a 24 horas após `issued_at`.

Ao perder autorização durante uma captura, o aplicativo DEVE encerrar o Pktmon
de forma segura, fechar o segmento corrente e preservar os brutos. NÃO DEVE
decodificar, exportar, enviar, apagar ou criptografar os arquivos.

### 5.1 Ponto único de autorização

O gate DEVE existir na camada compartilhada, não somente na interface:

- captura e monitores;
- ingestão/leitura;
- `ExportEngine.export`;
- exportação legada;
- autoexportação;
- upload rápido e envio de subsessão;
- automações acionadas por atalhos.

Chamadas diretas ao motor sem licença válida DEVEM falhar antes de criar ou
alterar arquivos de saída. O servidor do site também DEVE introspectar a lease
v2 e rejeitar product/audience/instalação/status divergentes.

## 6. Estado local e filesystem

### 6.1 Estado de licença

- `installation_id` é UUID aleatório por instalação.
- Hardware fingerprinting NÃO entra na 1.0.
- A chave de acesso digitada NÃO DEVE ser persistida.
- Lease, maior horário aceito e maior `release_sequence` visto DEVEM ser
  protegidos por DPAPI e ACL.
- DPAPI `LOCAL_MACHINE` só é permitido em arquivo legível e gravável por
  Administradores/SYSTEM.
- Chaves públicas pinadas ficam no binário e NÃO no estado mutável.

### 6.2 ACLs

- Código e dados de confiança: Administradores/SYSTEM.
- Estado de licença, staging de update e anti-downgrade:
  Administradores/SYSTEM.
- Preferências, banco, cache, logs e capturas podem ser graváveis pelo usuário.
- O aplicativo NÃO DEVE executar ou carregar código de diretório gravável pelo
  usuário.
- O instalador NÃO DEVE conceder `users-modify` a diretório que contenha ou
  possa fornecer EXE, DLL, script, plugin, chave pinada ou instalador.

`icacls` faz parte do teste de instalação.

## 7. Manifesto e atualização v2

### 7.1 Campos obrigatórios

```json
{
  "manifest_version": 2,
  "product": "rf-qol",
  "channel": "stable",
  "architecture": "windows-x64",
  "version": "1.0.0",
  "release_sequence": 1,
  "published_at": "UTC ISO-8601",
  "expires_at": "UTC ISO-8601",
  "key_id": "update-AAAA-NN",
  "file": "RF QOL Setup 1.0.0.exe",
  "size": 0,
  "sha256": "hexadecimal de 64 caracteres",
  "rollback_compatible_from": [],
  "signature": "Ed25519 base64url"
}
```

O cliente DEVE validar assinatura, todos os campos fechados, tamanho, SHA-256,
produto, canal, arquitetura, expiração do manifesto e sequência. Campos
desconhecidos críticos ou formato ambíguo falham fechado.

O feed não é fonte de confiança. O cliente seleciona somente manifesto válido
e rejeita update com `release_sequence` menor ou igual ao maior já instalado,
exceto rollback explícito e assinado.

O update normal usa `update-manifest.json`. A partir da segunda release, ela
também publica `rollback-manifest.json`, assinado no mesmo formato, apontando
para o instalador completo da versão imediatamente instalada antes do update.
Nesse manifesto dedicado, `rollback_compatible_from` declara as versões novas
cujos dados/schema podem voltar ao instalador anterior.

### 7.2 Download e execução

- Download ocorre em staging admin-only.
- Arquivo parcial tem nome distinto e nunca é executado.
- Tamanho e SHA-256 são verificados após download.
- Manifesto Ed25519, tamanho e SHA-256 são reverificados imediatamente antes
  da execução.
- A interface informa que o instalador não usa assinatura de código do Windows.
- A interface exibe versão, canal e changelog e exige confirmação.
- Não existe update silencioso.
- TLS padrão permanece obrigatório; `verify=False` ou equivalente é proibido.

## 8. Rollback

- Copiar e abrir o executável instalado numa pasta gravável é proibido.
- O rollback usa o instalador completo da versão anterior.
- Antes de baixar a nova versão, o cliente exige na mesma release o manifesto
  dedicado de rollback, ainda dentro da validade, e confirma que versão e
  sequência do alvo são exatamente as atualmente instaladas.
- O instalador anterior fica em cache admin-only com o manifesto dedicado e
  sua assinatura original.
- Antes de executar rollback, o cliente repete verificação Ed25519, tamanho,
  SHA-256, expiração, sequência inferior e presença da versão atual em
  `rollback_compatible_from`.
- Rollback exige confirmação e UAC.
- O anti-downgrade só é dispensado para esta ação explícita; as demais
  verificações continuam obrigatórias.
- Se o manifesto não declarar compatibilidade da versão/schema atual, o
  rollback é bloqueado e o usuário recebe instrução de recuperação.
- Antes de alterar dados, deve existir backup verificável e compatível.

## 9. Privacidade e captura passiva

- Captura primária: Pktmon nativo.
- Npcap só pode entrar após licença OEM e gate específico.
- É proibido injetar DLL, abrir/escrever memória do jogo, criar thread remota,
  instalar hook invasivo, desativar Defender ou usar ofuscação agressiva/UPX.
- `0x0101`, token, ticket, senha, chave de licença, Service Token do Cloudflare
  e credencial não podem ser persistidos ou exibidos.
- Diagnóstico é sanitizado, limitado em tamanho e enviado somente após
  consentimento.
- Logs são rotativos e redigidos antes da escrita, inclusive exceções.
- O link do Discord usa allowlist HTTPS exata e navegador padrão; não há webview
  embutida nem abertura automática.

## 10. Emissor e site

O emissor de licença DEVE:

- criar somente licenças novas do produto `rf-qol`;
- assinar lease v2 com a chave online de lease;
- limitar `valid_until` a 24 horas;
- vincular lease ao `installation_id` aleatório;
- não registrar a chave de acesso em texto claro;
- aplicar rate limit e trilha de auditoria sem segredo;
- oferecer validação e introspecção v2.

O site DEVE rejeitar lease antiga, produto/audience divergente, instalação
divergente, expiração e revogação. Indisponibilidade do emissor não pode ser
interpretada como licença válida no servidor.

## 11. Build e release

- Dependências de runtime e build devem ter versões e hashes fechados.
- Build ocorre em ambiente limpo a partir de commit limpo.
- Release inclui SBOM e arquivo de procedência.
- Scan de segredos e scanner de dados proibidos devem passar.
- Executável e instalador permanecem sem Authenticode por decisão do owner.
- A procedência declara explicitamente `authenticode=false`.
- Hashes publicados devem ser calculados sobre os bytes finais.
- Manifesto é assinado por último, com o hash do instalador final.
- Release pública sem manifesto v2, procedência Ed25519 ou testes negativos é
  proibida.

## 12. Critérios de aceite obrigatórios

### Licença

- Lease válida é aceita somente pela chave pinada correta.
- Chave inserida em `license.dat` não autoriza lease forjada.
- Lease assinada pela chave de update é rejeitada.
- Lease v1, produto errado, audience errada e outra instalação são rejeitados.
- Matriz de tempo prova funcionamento até 23:59:59 e bloqueio no limite de 24h.
- Recuo do relógio não estende o prazo.
- Revogação online bloqueia imediatamente.
- Sem licença, chamada direta aos motores de captura/processamento/exportação
  falha sem criar saída.

### Update e rollback

- Manifesto forjado, expirado, canal/produto errado, sequence antigo, tamanho ou
  hash divergente são rejeitados.
- Instalador ausente do manifesto Ed25519 ou com tamanho/hash divergente é
  rejeitado.
- Executável e instalador finais são confirmados como `NotSigned`, conforme a
  decisão registrada, sem tratar metadados de empresa como prova criptográfica.
- Nenhum código executável fica em caminho `users-modify`.
- Substituir o arquivo após a primeira verificação é detectado na reverificação.
- Rollback válido reinstala uma versão compatível; rollback incompatível é
  bloqueado sem alterar dados.

### Privacidade e release

- Scanner não encontra token, ticket, `0x0101`, licença ou credencial em banco,
  arquivos, IPC, logs e diagnóstico.
- Regressão completa do cliente passa.
- Self-test do executável instalado passa.
- Instalação limpa é validada em Windows 10 e 11 x64.
- Fluxo real ativação -> offline -> renovação -> revogação passa em staging.
- Upload real é aceito com lease v2 e rejeitado com lease antiga.

## 13. Gates do owner

- G0: aprovado em 09 ago 2026.
- G1: aprovado para implementação isolada, staging e chaves de desenvolvimento.
- G2: certificado Authenticode removido do escopo por decisão do owner; resta a
  cerimônia das chaves Ed25519 definitivas.
- G3: aprovado para RC e testes locais que não afetem o programa em uso.
- G4: pendente; publicação/release e produção não fazem parte desta autorização.

Nenhum gate autoriza automaticamente o seguinte.
