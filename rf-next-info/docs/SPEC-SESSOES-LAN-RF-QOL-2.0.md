# RF QOL 2.0 — Consulta de sessões entre computadores da rede local

Status: contrato de rede em planejamento, criado em 2026-08-16 e atualizado em
2026-08-17. A coleção local já pergunta a origem ao adicionar e permite remover
clientes da interface sem apagar dados. Nenhuma porta de rede, regra de
firewall, pareamento, banco remoto ou API LAN foi implementada.

## Objetivo da primeira entrega

Permitir que uma instalação do RF QOL consulte, em um ou mais computadores da
mesma rede local, resumos sanitizados das sessões do programa. A primeira entrega é
somente leitura e cobre:

- experiência e nível;
- início, fim, duração e atualização mais recente;
- recursos obtidos ou observados;
- resumo de combate e alvo atual, quando houver evidência recente.

O computador consultado é o **provedor**. O computador que reúne e apresenta as
informações é o **visualizador**. Ambos continuam armazenando seus próprios
dados localmente; o visualizador não cria uma réplica do banco do provedor.

## Escopo funcional inicial

O visualizador poderá:

1. começar com um espaço para o primeiro cliente exibido;
2. usar **Adicionar cliente** para escolher um cliente local ou um cliente
   externo recebido pela API;
3. quando a origem for externa, selecionar um computador já pareado e um dos
   clientes disponíveis em sua sessão;
4. criar novos espaços de cliente conforme a necessidade;
5. listar a sessão ativa e as sessões concluídas mais recentes;
6. abrir o resumo de uma sessão;
7. atualizar a sessão ativa periodicamente;
8. mostrar quando o computador, o cliente, a sessão ou uma métrica estiver
   indisponível ou desatualizada;
9. remover um cliente da interface sem apagar sua sessão de origem;
10. revogar um computador pareado a qualquer momento.

### Quantidade e origem dos clientes exibidos

- a configuração inicial apresenta um único espaço de cliente;
- o usuário adiciona outros individualmente conforme o uso;
- não existe teto funcional predefinido para clientes adicionados;
- cada cliente possui `source=local`, `source=emulator` ou
  `source=remote_api`;
- **Adicionar cliente** é a ação única para as três origens;
- um cliente `remote_api` referencia um computador pareado, um identificador
  público de cliente e a sessão remota atual, sem copiar o banco;
- adicionar um cliente não cria uma thread, conexão ou cache permanente;
- quantidade cadastrada e quantidade consultada simultaneamente são conceitos
  separados;
- concorrência, frequência e cache obedecem ao orçamento de RAM e continuam
  limitados mesmo quando houver muitos clientes adicionados;
- remover um cliente externo retira apenas seu cartão/aba; o computador continua
  pareado até uma revogação explícita;
- revogar um computador torna indisponíveis todos os clientes externos ligados
  a ele, sem apagar os últimos resumos já persistidos no provedor.

**Computador remoto** é a instalação provedora pareada. **Cliente externo** é um
cliente/personagem oferecido por esse computador e adicionado à coleção visual
do RF QOL. Um mesmo computador remoto pode oferecer mais de um cliente externo.

Clientes externos não consomem as duas vagas locais do Módulo Mapa. Na 2.0,
nenhum cliente local, emulador ou externo consome cota de quantidade da licença;
os módulos e suas ações continuam exigindo lease ativa e a feature
correspondente. Limites técnicos de captura, RAM e concorrência permanecem.

### Licenciamento 2.0

- prover, parear, consultar ou exibir sessões pela rede exige lease v3 ativa e a
  feature `sessions-lan`;
- a feature cobre o resumo remoto aprovado de EXP, nível, tempo, recursos e
  combate, além da origem **Externo via API**;
- o resumo mínimo de combate não libera as telas, overlays, bancos nem detalhes
  de `monitor-pve`, `monitor-pvp` ou `monitor-boss`;
- `base` continua obrigatória, e remover `sessions-lan` interrompe novas
  consultas sem apagar sessões armazenadas pelo provedor;
- o provedor e o visualizador validam o gate no núcleo da operação; esconder a
  opção na interface não é o único controle.

Proposta para a primeira entrega: até 20 sessões recentes por computador, com
paginação para buscar mais. Esse número é limite de apresentação e resposta,
não uma política de exclusão do banco local.

## Arquitetura

A consulta usa o modelo **pull**:

1. o provedor continua produzindo os resumos a partir do SQLite e dos redutores
   já existentes;
2. uma API LAN dedicada transforma esses resumos em um contrato sanitizado;
3. o visualizador consulta a lista e os detalhes sob demanda;
4. somente o cliente externo selecionado mantém o detalhe da sessão ativa sendo
   verificado a cada 5 segundos;
5. os demais clientes externos não mantêm detalhe vivo: disponibilidade e lista são
   atualizadas sob demanda ou por uma fila escalonada de baixa frequência;
6. `ETag`/`If-None-Match` permite responder `304 Not Modified` quando nada
   mudou.

A API LAN será separada de `LocalOutputApi`. A API atual continuará limitada a
`127.0.0.1`; ela não deve ser convertida em API remota apenas alterando o bind.
Nenhuma das duas APIs cria decoder, captura ou fluxo paralelo.

### Coleção unificada de clientes na interface

A camada visual usará uma entrada estável por cliente adicionado:

- `view_client_id`: ID local da entrada visual;
- `source`: `local`, `emulator` ou `remote_api`;
- `label`: nome apresentado pelo usuário/programa;
- para origem local: referência ao `client_key` já existente;
- para origem externa: `device_id` + `characters[].id` opacos;
- `capabilities`: conjunto explícito de ações disponíveis para aquela origem.

Essa camada é um adaptador de apresentação. Ela não renomeia chaves do decoder,
não transforma cliente externo em conexão local e não permite que dados remotos
entrem no Módulo Mapa, na captura ou nos bancos locais. Entradas locais
continuam obedecendo às capacidades técnicas e de licença existentes; entradas
externas da primeira entrega possuem apenas `sessions:read`.

## Ativação e pareamento

- acesso pela rede vem desligado por padrão;
- o usuário escolhe uma interface de rede marcada como privada pelo Windows;
- o provedor escuta somente no endereço privado selecionado, em porta dedicada;
- a regra de entrada do firewall é criada somente após confirmação explícita e
  apenas para o perfil privado;
- a janela de pareamento dura no máximo cinco minutos e pode ser encerrada
  antes pelo usuário;
- uma chave temporária de alta entropia autentica e fixa a impressão digital do
  certificado local do provedor;
- após o pareamento, cada visualizador recebe credencial exclusiva com a
  permissão `sessions:read`;
- certificado e credencial são exclusivos dessa integração e protegidos no
  Windows; credenciais de licença, Profile ou API local nunca são reutilizadas;
- o provedor mantém uma lista simples de computadores autorizados, último
  acesso e botão **Revogar**.

Descoberta automática por broadcast, multicast ou mDNS fica fora do primeiro
ciclo. O começo por endereço/hostname informado pelo usuário reduz exposição,
regras de firewall e ambiguidades com VPNs. Descoberta automática poderá ser
avaliada depois do ensaio real.

## Rotas propostas

### `GET /api/v1/lan/health`

Retorna apenas disponibilidade do provedor e compatibilidade do contrato:

- `schema` e `schema_version`;
- `device_id` opaco e apelido escolhido pelo usuário;
- versão do RF QOL;
- horário de geração;
- disponibilidade da leitura de sessões.

Não retorna hostname do Windows, usuário, IPs, licença, caminhos, processos,
portas do jogo ou estado bruto da captura.

### `GET /api/v1/lan/sessions`

Parâmetros iniciais:

- `state=active|completed|all`, com `all` como padrão;
- `limit`, padrão 20 e máximo 50;
- `cursor`, opaco e estável somente para aquela consulta.

Retorna itens compactos suficientes para a lista: ID público, estado, horários,
duração, clientes/personagens com seus IDs públicos, nível, EXP obtida e idade
da última atualização. Essa lista alimenta a opção **Externo via API** dentro de
**Adicionar cliente**.

### `GET /api/v1/lan/sessions/{public_session_id}`

Retorna o detalhe sanitizado de uma sessão. O identificador público é derivado
por HMAC com segredo da instalação; o `session_id` local nunca sai do provedor.

Não haverá `POST`, `PUT`, `PATCH`, `DELETE`, WebSocket ou comando remoto nesta
entrega.

## Contrato proposto

```json
{
  "schema": "rf-qol.lan.session",
  "schema_version": 1,
  "generated_at": "2026-08-16T18:30:00Z",
  "device": {
    "id": "dev_opaque",
    "alias": "PC Farm 1"
  },
  "session": {
    "id": "ses_opaque",
    "state": "active",
    "started_at": "2026-08-16T16:00:00Z",
    "ended_at": null,
    "duration_seconds": 9000,
    "updated_at": "2026-08-16T18:29:58Z",
    "stale": false,
    "characters": [
      {
        "id": "cli_opaque",
        "slot": "a",
        "name": "Personagem",
        "level": 55,
        "experience": {
          "current": 123456,
          "current_percent": 42.5,
          "missing_for_next_level": 167544,
          "gained_in_session": 25000,
          "gained_percent_in_session": 8.6,
          "gained_per_hour": 10000
        },
        "resources": {
          "credits_gained": 480000,
          "contribution_gained": 120,
          "diamonds_current": null,
          "loot_items": 18,
          "loot_by_rarity": {
            "common": 10,
            "uncommon": 5,
            "rare": 3,
            "epic": 0
          }
        },
        "combat": {
          "activity": "pve",
          "mob_kills_estimated": 24,
          "finalizations": 24,
          "current_target": {
            "kind": "monster",
            "name": "Alvo confirmado",
            "level": 54,
            "hp_percent": 63.2,
            "age_seconds": 1.4,
            "stale": false
          }
        }
      }
    ],
    "quality": {
      "identity": "confirmed",
      "experience": "confirmed",
      "resources": "partial",
      "combat": "recent"
    }
  }
}
```

O exemplo demonstra formato, não valores garantidos. Campos sem evidência são
`null`; não se convertem em zero, `false`, nível presumido ou estado ocioso.

`characters[].id` identifica de forma opaca o cliente oferecido pelo provedor.
Ele é estável dentro daquele provedor para permitir que **Adicionar cliente**
mantenha o vínculo entre atualizações e sessões, mas não contém nem expõe UID do
personagem, `client_key` local ou `session_id`.

## Semântica dos campos

### Experiência e nível

- `level`, `current`, `current_percent` e ganho usam somente eventos já
  reconhecidos pelo decoder e o resumo persistido atual;
- `gained_in_session` é o acumulado da sessão, não o Top 100 do servidor;
- `gained_per_hour` só existe com duração válida e EXP observada;
- mudança de nível não autoriza inferir um nível inicial que não tenha sido
  registrado;
- informação ausente permanece `null`.

### Tempo

- horários usam UTC em ISO 8601;
- `duration_seconds` exclui pausas quando essa informação estiver confirmada;
- sessão ativa usa o relógio do provedor, nunca o relógio do visualizador;
- diferença de relógio entre computadores não altera a duração calculada;
- `stale=true` quando a sessão ativa não recebe atualização dentro do TTL
  definido pelo contrato.

### Recursos

- `credits_gained` e `contribution_gained` são deltas acumulados na sessão;
- `diamonds_current` é saldo observado, não ganho da sessão, e fica `null` se
  não houver snapshot confiável;
- loot é contagem confirmada de itens observados, agrupada por raridade;
- inventário completo, slots, refinamento e lista detalhada dos itens não saem
  na primeira entrega;
- cada grupo possui qualidade própria para distinguir zero confirmado de dado
  não observado.

### Combate

- `mob_kills_estimated` mantém o nome e a semântica de proxy por recompensa;
  nunca será apresentado como kill confirmada;
- `finalizations` mantém o contador já derivado pelo resumo atual;
- `activity` aceita `idle`, `pve`, `pvp`, `boss` ou `unknown`;
- `current_target` é somente o alvo atual sanitizado e recente;
- sessão concluída retorna `current_target=null`;
- listas de jogadores próximos, guildas, coordenadas, UIDs, dano por jogador e
  eventos individuais não fazem parte deste contrato;
- a primeira entrega não tenta reconstruir histórico completo de alvos ou dano
  acumulado que o programa ainda não confirme como métrica de sessão.

## Privacidade e segurança

- TLS obrigatório com certificado local por instalação e impressão digital
  fixada no pareamento;
- autenticação obrigatória em todas as rotas, inclusive `health`;
- credencial longa, aleatória, individual por par e comparada em tempo
  constante;
- acesso restrito à interface privada selecionada e ao mesmo segmento de rede;
- sem CORS e sem conteúdo executável;
- máximo inicial de quatro requisições simultâneas, 10 requisições por segundo
  por par e 256 KiB por resposta;
- esses limites controlam trabalho simultâneo e proteção do provedor; não
  limitam quantos clientes remotos o usuário pode cadastrar;
- erros nunca incluem traceback, caminho, consulta SQL ou identificador local;
- logs guardam somente dispositivo opaco, ação, resultado e horário; a
  credencial nunca é registrada;
- `session_id`, UID, fluxo, porta, pacote, payload bruto, token, ticket,
  credencial, licença e `0x0101` são proibidos nas respostas;
- a API não pode iniciar, pausar, finalizar, apagar, exportar ou configurar uma
  sessão;
- revogação invalida imediatamente a credencial daquele visualizador.

## Memória, disco e tráfego

- a resposta é projetada sob demanda a partir de consultas limitadas no
  SQLite; não se carrega toda a sessão nem todo o histórico em RAM;
- o provedor pode manter somente o último documento serializado e seu `ETag`,
  dentro do orçamento de memória escolhido pelo usuário;
- o visualizador mantém em memória quente somente o detalhe do cliente externo
  selecionado; os demais conservam apenas metadados mínimos de lista/saúde;
- o cadastro completo permanece em armazenamento local e a interface carrega
  somente a página visível, com busca por nome, origem ou computador;
- não existe thread, conexão aberta ou histórico residente dedicado para cada
  cliente cadastrado;
- consultas de clientes não selecionados passam por uma fila limitada e
  escalonada; mais cadastros podem aumentar a idade entre atualizações, mas não
  a concorrência nem o cache acima do orçamento;
- paginação impede carregar todas as sessões de uma vez;
- nenhuma sessão remota é persistida localmente no primeiro ciclo;
- computador offline gera estado próprio e não conserva dados vivos como se
  fossem atuais;
- o perfil de RAM reduz primeiro cache e frequência de atualização, nunca
  remove campos silenciosamente de uma mesma versão do contrato.

## Interface proposta

Em **Integrações**, adicionar a seção **Computadores da rede**:

- **Ativar compartilhamento de sessões neste computador**;
- interface privada e porta selecionadas;
- **Permitir pareamento por 5 minutos**;
- computadores autorizados, último acesso e **Revogar**;
- **Adicionar computador**, com endereço, chave temporária e apelido;
- cada computador pareado mostra quantos clientes externos estão disponíveis e
  quantos já foram adicionados à coleção visual;
- revogar o computador invalida seus clientes externos, mas pede confirmação e
  não afeta clientes locais.

Na área comum de seleção de clientes, manter um único botão **Adicionar
cliente**. O fluxo apresenta:

1. **Neste computador** — cliente PC ou emulador local detectado e ainda não
   adicionado;
2. **Externo via API** — computador pareado, cliente público disponível e
   sessão atual correspondente.

Regras da coleção visual:

- a primeira abertura apresenta um espaço de cliente; se houver um local
  elegível, ele pode ocupá-lo, senão permanece vazio;
- cada uso de **Adicionar cliente** cria um cartão/aba de origem local ou
  externa;
- a combinação `device_id + characters[].id` impede adicionar o mesmo cliente
  externo duas vezes;
- cliente externo mostra o selo **Externo · API · <apelido do computador>**;
- EXP, nível, tempo, recursos e combate usam a mesma organização visual dos
  clientes locais;
- captura, iniciar/pausar/finalizar sessão, mapa, alarmes, bancos, inventário e
  demais comandos locais ficam indisponíveis no cartão externo nesta entrega;
- remover o cartão externo não revoga o computador nem apaga a sessão remota;
- a lista usa paginação ou virtualização para não criar todos os cartões e
  widgets simultaneamente.

Em **Sessões**, adicionar o filtro de origem:

- **Este computador**;
- cada computador pareado pelo apelido;
- cada cliente externo já adicionado, junto dos clientes locais, no seletor
  comum;
- estado online/offline, última atualização e aviso de dados desatualizados;
- a mesma organização visual de EXP, tempo, recursos e combate, sem misturar
  totais de computadores diferentes.

## Falhas e estados esperados

- `401`: credencial ausente ou inválida;
- `403`: par revogado, escopo insuficiente ou origem fora da rede permitida;
- `404`: sessão pública inexistente ou já fora da janela consultável;
- `409`: versão de contrato incompatível;
- `429`: limite de consulta atingido;
- `503`: banco bloqueado temporariamente ou resumo indisponível.

O visualizador preserva o último resumo apenas como referência visual, marcado
com horário e `stale=true`; ele nunca o apresenta como leitura atual.

## Fora da primeira entrega

- descoberta automática de computadores;
- acesso pela internet, nuvem, site, relay ou redirecionamento de porta;
- envio contínuo/push ou WebSocket;
- espelhamento, sincronização ou união dos bancos SQLite;
- mapa, coordenadas e jogadores próximos;
- inventário detalhado, drops individuais e Banco PvE/PvP/Leilão;
- ranking Top 100 do servidor;
- controle remoto da captura, sessão, alertas ou configurações;
- edição, exclusão, exportação ou upload de sessões remotas.

## Etapas propostas de implementação

1. criar a projeção sanitizada e estável de uma sessão local, ainda sem rede;
2. cobrir projeção, `null`, IDs opacos, paginação, limites e ausência de
   vazamentos com testes automáticos;
3. criar servidor LAN separado, TLS, credenciais por par e revogação;
4. criar o cliente de consulta com `ETag`, timeout, backoff e cache limitado;
5. adicionar a coleção unificada e expansível, com **Adicionar cliente** para
   origem local, emulador ou **Externo via API**;
6. validar automaticamente isolamento, autorização, incompatibilidade de
   schema, volume configurável de cadastros, concorrência fixa, quantidade de
   threads/widgets, capacidades por origem e pressão de memória;
7. somente no executável candidato, realizar o ensaio manual entre dois
   computadores da mesma rede e validar firewall/rollback.

## Gates antes de implementar

Recomendação inicial sujeita à confirmação do owner:

1. resolvido: começar com um espaço de cliente e permitir adicionar outros sem
   teto funcional predefinido;
2. resolvido: cliente externo recebido pela API entra pela mesma opção
   **Adicionar cliente** usada pela coleção local;
3. começar por endereço manual e pareamento, deixando descoberta automática
   para uma etapa futura;
4. listar a sessão ativa e as 20 concluídas mais recentes por computador;
5. tratar recursos como deltas de créditos/contribuição/loot e saldo atual de
   diamantes explicitamente rotulado;
6. compartilhar nome do personagem, mas nunca UID;
7. restringir o primeiro ciclo a IPv4 e perfil privado do Windows;
8. resolvido: cliente externo não consome cota de quantidade; a licença libera
   módulos por feature;
9. resolvido: toda operação LAN usa `sessions-lan`, sem desbloquear os monitores,
   conforme `SPEC-LICENCA-RF-QOL-2.0.md`.

Implementação da API LAN exige autorização específica após estes pontos. Criar
regra de firewall, realizar ensaio manual, gerar executável, publicar ou expor
qualquer serviço continuam gates separados.

## Rollback planejado

Desativar **Compartilhar sessões na rede** encerra o servidor, remove a regra
de firewall dedicada e invalida os pares. A API local em `127.0.0.1`, captura,
decoder, SQLite e telas de sessões locais permanecem inalterados. A remoção do
módulo remove as entradas `remote_api` da coleção visual sem apagar sessões nem
modificar o banco de captura; clientes locais e emuladores permanecem.
