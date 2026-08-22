# Plano inicial — RF QOL Web Based

Data: 22 ago 2026  
Branch: `feat/rf-qol-web-based`  
Estado: W0 concluído tecnicamente; fundação local de W1 em implementação
Base preservada: `rf-qol-desktop-2.0.0-beta.6` / commit `795333d`  
Autorizado em 22 ago 2026: avançar a base local do Agent Windows, incluindo
identidade DPAPI e transporte HTTPS testável.
Ainda não autoriza: habilitar envio real, registrar instalação em produção,
servidor, migração, infraestrutura, DNS, deploy, publicação ou instalador.

## 1. Decisão do owner

A nova linha do RF QOL será dividida assim:

- **computador:** captura passiva, reagrupamento TCP, decode, correlação mínima
  necessária para identificar o cliente, sanitização, fila offline e envio;
- **servidor dedicado:** processamento dos eventos decodificados, estado vivo,
  sessões, subsessões, status, monitores, agregações, históricos, bancos
  autorizados, APIs e painel;
- **navegador:** visualização e configuração dos recursos permitidos do Profile;
- **versão desktop atual:** permanece preservada e utilizável como rollback.

O servidor será a fonte autoritativa dos dados processados. O computador não
enviará pacotes brutos e não haverá um segundo decoder no servidor.

## 2. Objetivo do primeiro ciclo

Entregar um corte vertical somente leitura que permita consultar, pelo site, em
um único Profile:

- computadores conectados e idade da última leitura;
- clientes/personagens separados por computador;
- sessão ativa e sessões concluídas;
- nível, EXP atual e progresso;
- EXP, créditos e contribuição ganhos na sessão;
- tempo de sessão;
- estado `Teleportando`, `PvP`, `Farm` ou `Ocioso`;
- resumo de combate PvE/PvP.

Mapa, drops, Boss, ranking Top 100 e bancos entram depois que identidade,
idempotência, memória, latência e isolamento multi-cliente estiverem aprovados.

## 3. Limite de responsabilidade

| Responsabilidade | Computador | Servidor | Painel web |
|---|---|---|---|
| Capturar tráfego com Pktmon | Autoritativo | Não recebe | Não recebe |
| Reagrupar fluxos TCP | Autoritativo | Não executa | Não executa |
| Decodificar protocolo | Autoritativo, decoder único | Não executa | Não executa |
| Correlacionar rota com cliente | Mínimo necessário ao evento | Valida continuidade | Exibe origem |
| Remover campos proibidos | Lista positiva antes do envio | Valida novamente | Nunca recebe |
| Persistir fila de saída | Temporária e limitada | Não aplicável | Não aplicável |
| Processar sessões e métricas | Somente compatibilidade durante migração | Autoritativo | Consulta |
| Calcular status e monitores | Somente shadow/fallback aprovado | Autoritativo | Consulta |
| Guardar histórico | Apenas outbox e diagnóstico limitado | Autoritativo | Consulta paginada |
| Configurar captura | Local | Não controla no MVP | Apenas mostra estado |
| Comandos remotos | Não no MVP | Não no MVP | Não no MVP |

## 4. Fluxo-alvo

```text
RF NEXT
   |
   v
Pktmon -> reagrupamento TCP -> decoder canônico -> evento normalizado
                                                   |
                                                   v
                                         filtro por lista positiva
                                                   |
                                                   v
                                      outbox SQLite limitada no PC
                                                   |
                                                   v
                                      HTTPS autenticado e idempotente
                                                   |
                                                   v
                                 API de ingestão RF QOL dedicada
                                                   |
                                  grava lote antes de confirmar
                                                   |
                                                   v
                                   processador de eventos no servidor
                                      |                         |
                                      v                         v
                               estado vivo                 históricos
                                      |                         |
                                      +------------+------------+
                                                   v
                                         API de consulta
                                                   |
                                                   v
                                             painel web
```

O aplicativo Windows nunca aguarda o processamento remoto para continuar a
captura. Recebimento, confirmação e compactação da outbox ocorrem fora da thread
da interface e fora do callback do Pktmon.

## 5. Evento normalizado no computador

O limite do Agent é um evento já decodificado, tipado e sanitizado. Exemplo
conceitual:

```json
{
  "schema": "rf-qol.decoded-event/v1",
  "event_id": "id-opaco-idempotente",
  "installation_id": "instalacao-publica",
  "stream_id": "fluxo-logico-opaco",
  "sequence": 18421,
  "occurred_at": "2026-08-22T12:00:00.123Z",
  "client_ref": "cliente-publico-ou-null",
  "type": "character.exp_changed",
  "payload": {
    "total_exp": 123456789
  },
  "evidence": {
    "confidence": "confirmed",
    "decoder_version": "1.29.x"
  }
}
```

Regras obrigatórias:

- `event_id` permanece estável em todo reenvio;
- `sequence` é monotônica por instalação/stream e permite detectar lacunas;
- evento sem cliente confirmado mantém `client_ref=null`;
- o servidor não inventa propriedade para evento sem identidade;
- schema e tipo possuem listas positivas próprias de campos;
- objeto interno do decoder nunca é serializado diretamente;
- atualização de catálogo não muda retroativamente o evento aceito;
- o servidor registra versão do decoder e do schema usados na origem.

## 6. Envelope e protocolo de envio

Contrato candidato:

```text
POST /api/qol/v1/ingest/batches
Content-Encoding: gzip opcional
Idempotency-Key: <batch_id>
```

```json
{
  "schema": "rf-qol.ingest-batch/v1",
  "batch_id": "id-opaco",
  "installation_id": "instalacao-publica",
  "sent_at": "2026-08-22T12:00:01Z",
  "first_sequence": 18421,
  "last_sequence": 18480,
  "events": []
}
```

Resposta mínima:

```json
{
  "batch_id": "id-opaco",
  "accepted": true,
  "accepted_through_sequence": 18480,
  "duplicate": false,
  "rejected_events": [],
  "server_time": "2026-08-22T12:00:02Z"
}
```

Limites iniciais de homologação:

- até 250 eventos ou 256 KiB descompactados por lote;
- flush a cada 1 segundo quando houver eventos;
- no máximo dois lotes simultâneos por instalação;
- timeout curto e reenvio com espera progressiva e variação aleatória;
- resposta parcial mantém somente os registros não confirmados na outbox;
- lotes fora de ordem podem ser armazenados, mas não promovidos para estado
  autoritativo até a lacuna ser resolvida ou expirar por política explícita.

Os valores serão recalibrados por medição; não são cotas comerciais.

### 6.1 Assinatura preparada no Agent

O cliente local já monta, mas não envia por padrão, os cabeçalhos:

- `Idempotency-Key`;
- `X-RFQOL-Installation-ID`;
- `X-RFQOL-Key-ID`;
- `X-RFQOL-Timestamp`;
- `X-RFQOL-Nonce`;
- `X-RFQOL-Body-SHA256`;
- `X-RFQOL-Signature`.

A assinatura Ed25519 usa o contexto `RFQOL-INGEST-V1`, método, caminho, lote,
horário, nonce e SHA-256 do JSON canônico antes de eventual gzip. O cliente
recusa HTTP, credenciais na URL e redirecionamentos. Nenhum bearer token,
lease, chave privada ou segredo de pseudonimização entra no request.

O contrato público de registro inclui chave pública, `key_id`, algoritmo e uma
prova de posse Ed25519 no contexto separado `RFQOL-REGISTER-V1`. O futuro
servidor ainda deverá vincular esse registro ao Profile autenticado; a prova de
posse sozinha não concede acesso.

## 7. Agent Windows

### 7.1 Permanece no Agent

- Pktmon e seleção de interfaces/rotas;
- reagrupamento e ressincronização TCP;
- decoder canônico;
- identidade canônica mínima de cliente;
- sanitização por lista positiva;
- outbox durável e limitada;
- autenticação da instalação;
- tela pequena de saúde: captura, servidor, fila, último envio e versão;
- diagnóstico sanitizado e contadores de descarte;
- atualização do próprio Agent somente pelo fluxo já autorizado.

### 7.2 Sai do Agent ao final da migração

- agregação definitiva de sessões e subsessões;
- cálculo definitivo de EXP/h, recursos/h e contribuição/h;
- classificação definitiva do status;
- estado vivo dos monitores PvE, PvP e Boss;
- históricos e bancos compartilhados;
- ranking consolidado;
- interface principal de consulta.

Durante a migração, os processadores desktop permanecem em **shadow mode** para
comparação e rollback. Eles não podem gravar no mesmo estado autoritativo do
servidor nem corrigir resultados remotos silenciosamente.

## 8. Servidor dedicado recomendado

A ingestão de alto volume não deve ser adicionada diretamente às rotas síncronas
do servidor monolítico atual nem ao mesmo SQLite de conteúdo do site.

Componentes lógicos iniciais:

1. **Gateway HTTPS:** domínio, TLS, limite de corpo e rate limit.
2. **API de ingestão:** autentica, valida schema, deduplica e grava o lote.
3. **Banco RF QOL:** eventos aceitos, recibos, estado vivo, sessões e projeções.
4. **Worker:** consome eventos gravados e atualiza redutores versionados.
5. **API de consulta:** aplica escopo de Profile e paginação.
6. **Painel web:** somente leitura no primeiro ciclo.

Implantação mínima recomendada para homologação:

- um serviço de API;
- um processo de worker;
- um PostgreSQL próprio do RF QOL, sem compartilhar o banco do Authentik;
- uma única imagem do serviço, com comandos diferentes para API e worker;
- nenhum Redis, Kafka ou conjunto de microserviços antes de medição justificar.

O site atual pode apontar uma rota protegida para a API nova, mas o processamento
RF QOL deve ter ciclo de migração, banco, backup e rollback independentes.

## 9. Modelo de dados inicial

Tabelas lógicas:

- `qol_profiles` — vínculo com a identidade do site;
- `qol_installations` — chave pública, versão, revogação e último contato;
- `qol_clients` — identidade pública e continuidade por instalação;
- `qol_ingest_batches` — recibo idempotente e intervalo de sequência;
- `qol_decoded_events` — evento permitido, particionável por tempo;
- `qol_live_state` — uma linha substituível por cliente;
- `qol_sessions` — ciclo e resumo autoritativo;
- `qol_session_counters` — métricas incrementais e checkpoints;
- `qol_processing_offsets` — posição do worker por instalação/stream;
- `qol_audit_log` — ações de segurança sanitizadas.

Regras de isolamento:

- toda tabela de negócio inclui `profile_id`;
- chaves e consultas impedem associação entre Profiles;
- `client_ref` é único apenas dentro da instalação/Profile corretos;
- eventos não atribuídos ficam separados e não entram em contadores por cliente;
- troca de porta, fluxo ou conexão não cria automaticamente outro personagem;
- correção de identidade ocorre somente com evidência canônica e auditoria.

## 10. Processadores do MVP

Ordem de processamento por evento:

1. validar continuidade e identidade;
2. atualizar presença do computador e cliente;
3. abrir, continuar ou finalizar a sessão lógica;
4. atualizar personagem, nível e EXP;
5. atualizar créditos e contribuição;
6. aplicar eventos de combate confirmados;
7. derivar status com prioridade
   `Teleportando > PvP > Farm > Ocioso`;
8. persistir novo estado vivo e checkpoint da sessão;
9. publicar mudança para a API/painel.

Semântica preservada:

- Farm: dano ou abate PvE confirmado nos últimos 30 segundos;
- PvP: dano positivo causado ou recebido de jogador;
- Teleportando: ciclo de teleporte confirmado ainda aberto;
- Boss continua sinal separado até seu processador entrar em fase posterior;
- ausência de evidência produz `unknown/null`, não `false` inventado.

## 11. Estado vivo e painel

O estado vivo é substituível; não cria uma linha histórica a cada atualização.

Estados de presença:

- `online`: heartbeat dentro do prazo;
- `delayed`: última atualização excedeu o SLA, mas ainda pode retornar;
- `offline`: prazo encerrado ou Agent finalizado;
- `unknown`: continuidade ou relógio não confiável.

MVP do painel:

- seletor de Profile autorizado;
- computadores com versão, saúde e última atualização;
- cards compactos por cliente;
- personagem, nível, EXP atual, status e tempo de sessão;
- EXP, créditos e contribuição da sessão;
- combate resumido;
- histórico de sessões paginado;
- selo explícito de origem e idade do dado;
- estado vazio, atrasado, incompleto e sem permissão distintos.

O painel não inicia captura, não altera monitor, não encerra sessão e não envia
comando ao jogo ou ao computador nessa fase.

## 12. Atualização em tempo real

Primeiro ciclo:

- Agent envia lotes por HTTPS;
- worker processa continuamente;
- painel usa atualização periódica curta ou SSE somente do servidor para o
  navegador;
- WebSocket bidirecional não é requisito do MVP.

Meta inicial de homologação:

- p95 do evento capturado até estado disponível no painel: até 3 segundos;
- p95 de ingestão HTTP: até 500 ms, sem esperar agregações demoradas;
- painel indica atraso quando a meta não é cumprida.

Overlays e sons são um gate separado. Se precisarem continuar funcionando sem
internet ou com latência subsegundo, será necessário manter um processador local
mínimo para esses sinais. Sem essa exceção aprovada, eles consumirão resultados
do servidor e ficarão indisponíveis durante perda de conexão.

## 13. Outbox, memória e modo offline

A outbox é persistida em SQLite separado do banco histórico desktop.

Regras:

- RAM contém somente lote em formação e lotes em voo;
- eventos confirmados são removidos/compactados da outbox;
- estados substituíveis podem colapsar para o mais recente sob pressão;
- finalização de sessão, drops confirmados e eventos Boss duráveis não são
  descartados silenciosamente;
- limite de RAM do usuário também reduz lote e concorrência;
- limite de disco e prazo offline são configuráveis dentro de faixas seguras;
- UI nunca consulta ou materializa toda a outbox;
- envio continua após reinício sem duplicar processamento.

Política candidata para homologação:

- outbox padrão: 512 MiB ou 7 dias, o que chegar primeiro;
- estado vivo repetido é compactável;
- eventos duráveis acima do limite bloqueiam novo histórico remoto com aviso,
  sem interromper captura local;
- nenhuma remoção definitiva é implementada antes de aprovação do owner.

## 14. Segurança e privacidade

### 14.1 Identidade

- Profile continua sendo a identidade do usuário;
- cada instalação gera par de chaves próprio;
- chave privada permanece protegida por DPAPI;
- servidor registra somente chave pública e identificador opaco;
- cada lote é autenticado e vinculado à instalação;
- revogação de uma instalação não revoga as demais;
- licença libera módulos, mas não substitui autenticação da ingestão.

### 14.2 Dados proibidos

Nunca enviar ou persistir remotamente:

- pacote, fluxo, ETL, PCAP ou payload bruto;
- token, ticket, senha, segredo ou chave privada;
- conteúdo do opcode `0x0101`;
- porta efêmera como identidade;
- caminho local, dump de memória ou traceback completo;
- objeto genérico do decoder sem schema permitido.

### 14.3 Privacidade

- dados são privados por padrão ao Profile;
- compartilhamento com guilda ou público é opt-in por domínio;
- mapa, coordenadas e nomes próximos exigem gate próprio;
- logs registram códigos e contadores, não conteúdo sensível;
- exportação e exclusão serão definidas antes da produção.

## 15. Migração sem regressão

### W0 — Contratos e corpus

- [x] materializar os schemas `decoded-event/v1` e `ingest-batch/v1` no Agent;
- [x] aplicar lista positiva inicial de tipos/campos e rejeitar `0x0101`,
  credenciais, IDs canônicos, fluxo, porta, payload e arquivos brutos;
- [x] criar corpus sintético sanitizado e testes de contrato;
- [x] definir relógio, sequência local, identidade opaca e idempotência;
- [x] criar outbox SQLite separada, deduplicada e limitada, sem descarte
  automático de eventos não confirmados;
- [x] integrar um sink opcional e não bloqueante após o decoder, isolando falhas
  para que captura e processamento desktop continuem funcionando;
- [x] manter criação da outbox e todo envio novo desligados por padrão;
- [x] gerar par Ed25519 por instalação e proteger chave privada e segredo de
  pseudonimização com DPAPI no escopo do usuário Windows;
- [x] preservar identidade por backup protegido e bloquear rotação silenciosa
  quando ambos os arquivos estiverem corrompidos;
- [ ] revisar a lista de eventos do MVP com o owner antes de congelar W0;
- [ ] medir volume real e completar corpus permitido sem incluir dados brutos.

Gate: revisão dos contratos e dados permitidos.

### W1 — Ingestão mínima em homologação

- [x] preparar contrato público de registro da instalação, sem chave privada;
- [x] preparar request HTTPS assinado por lote, com timestamp, nonce,
  idempotência e SHA-256, sem bearer token ou lease;
- [x] preparar worker local de entrega com ACK parcial, backoff, limites e
  diagnóstico sanitizado, sem iniciá-lo por padrão;
- [ ] registrar instalação no servidor de homologação;
- [ ] aceitar lote autenticado e idempotente;
- [ ] armazenar recibo e eventos sanitizados;
- [ ] comprovar rejeição de campos proibidos e limites no servidor;
- [x] manter esta fase sem processamento de domínio ou painel real.

Gate: segurança, backup e rollback do banco de homologação.

### W2 — Primeiro processador vertical

- presença, cliente, sessão, nível, EXP, créditos e contribuição;
- status básico e combate resumido;
- API de consulta privada;
- painel somente leitura.

Gate: dois computadores, múltiplos clientes e isolamento comprovados.

### W3 — Shadow mode e equivalência

- desktop e servidor processam o mesmo corpus sem compartilhar estado;
- relatório compara evento a evento e snapshot a snapshot;
- divergências são classificadas por semântica, identidade, ordem ou atraso;
- nenhuma tela desktop é removida.

Gate: zero mistura entre clientes e equivalência aprovada dos campos do MVP.

### W4 — Offline, carga e estabilidade

- reinício do Agent com outbox pendente;
- lote duplicado, parcial, atrasado e fora de ordem;
- indisponibilidade do banco/worker;
- ensaio de 10 h com pelo menos dois clientes;
- memória do Agent respeitando o limite escolhido;
- crescimento, latência e recuperação do servidor medidos.

Gate: SLOs, retenção e capacidade aprovados.

### W5 — Migração da interface principal

- site vira interface autoritativa dos recursos do MVP;
- Agent mantém somente captura, conectividade, fila e diagnóstico;
- versão desktop continua disponível como rollback;
- rotas antigas permanecem durante janela de compatibilidade aprovada.

Gate: aceitação visual/funcional e plano de rollback ensaiado.

### W6 — Domínios especializados

Em cortes independentes:

1. mapa e região;
2. drops próprios e anunciados;
3. Boss e ranking acumulado por jogador/guilda;
4. Banco PvE;
5. Ranking Top 100;
6. PvP e Leilão quando a política da versão correspondente permitir.

Cada domínio exige schema, retenção, permissão, teste específico e regressão.

### W7 — Produção

- infraestrutura aprovada;
- backup/restauração ensaiados;
- observabilidade e alertas;
- migração aditiva por grupo de teste;
- rollback para desktop;
- deploy, publicação e instalador autorizados separadamente.

## 16. Critérios de aceite do MVP

- computador encerra sua responsabilidade no evento decodificado/sanitizado;
- servidor nunca recebe pacote bruto nem executa decoder do protocolo;
- mesmo lote reenviado não duplica contadores;
- eventos de clientes diferentes nunca se misturam;
- evento sem identidade permanece sem atribuição;
- troca de fluxo preserva o cliente somente com evidência canônica;
- processamento continua após reinício do worker exatamente do offset salvo;
- painel diferencia dado atual, atrasado, offline e desconhecido;
- perda da internet não trava captura nem interface do Agent;
- outbox respeita limites de RAM e disco;
- Profile não consulta instalações ou clientes de outro Profile;
- revogação impede novos envios sem apagar histórico automaticamente;
- nenhum dado proibido aparece em request, banco, resposta ou log;
- p95 ponta a ponta atende a meta aprovada;
- duas ou mais instalações funcionam simultaneamente;
- testes específicos e regressão completa passam em cada corte;
- versão desktop beta.6 continua disponível como rollback até o aceite final.

## 17. Métricas operacionais

Agent:

- eventos decodificados, permitidos, rejeitados e enfileirados;
- bytes/linhas da outbox;
- sequência mais antiga e mais recente;
- lotes em voo, tentativas e último ack;
- descartes por tipo e pressão de memória;
- idade do evento durável mais antigo.

Servidor:

- lotes e eventos recebidos/aceitos/rejeitados/duplicados;
- latência e tamanho por lote;
- atraso entre sequência aceita e processada;
- falhas e reinícios do worker;
- clientes online/delayed/offline;
- tamanho das tabelas e crescimento diário;
- consultas lentas, violações de escopo e revogações.

## 18. Riscos principais

1. Enviar eventos decodificados em volume próximo ao pacote bruto e transferir o
   problema de memória para rede/banco.
2. Processar eventos fora de ordem e alterar EXP, status ou sessão.
3. Misturar clientes após rotação de fluxo ou reconexão.
4. Tornar overlays e sons dependentes de internet sem decisão explícita.
5. Usar o SQLite monolítico atual para ingestão de alto volume.
6. Manter processadores desktop e servidor ativos indefinidamente e criar duas
   verdades conflitantes.
7. Crescimento sem retenção de eventos aceitos.
8. Expor localização, proximidade ou nomes além do Profile autorizado.
9. Confirmar lote antes da gravação durável e perder eventos após falha.
10. Realizar migração grande sem shadow mode e rollback desktop.

## 19. Gates pendentes do owner

1. **MVP:** confirmar que o primeiro corte contém somente presença, clientes,
   sessão, EXP, nível, tempo, recursos, status e combate resumido.
2. **Overlay/sons:** escolher entre dependência do servidor ou processador local
   mínimo para continuidade offline e baixa latência.
3. **Retenção:** aprovar prazos para eventos decodificados, sessões e auditoria.
4. **Outbox:** aprovar limite inicial de 512 MiB/7 dias ou definir outro.
5. **Infraestrutura:** aprovar serviço e PostgreSQL próprios do RF QOL.
6. **Identidade:** aprovado e implementado localmente com Ed25519 e DPAPI por
   usuário; registro da chave pública no servidor continua pendente.
7. **Domínio:** aprovar posteriormente os destinos de painel/API; nenhum DNS é
   criado por este plano.
8. **Privacidade:** decidir quais campos de mapa, coordenadas e proximidade podem
   sair do computador.
9. **Compatibilidade:** definir por quanto tempo desktop e rotas antigas ficam
   disponíveis.
10. **Produção:** staging, deploy, publicação e cutover continuam gates
    independentes.

## 20. Próximo gate recomendado

Fechar W0 antes de implementar qualquer serviço:

1. catálogo dos tipos de evento do MVP;
2. schema de cada payload e lista de campos proibidos;
3. regras de sequência, relógio, idempotência e cliente não identificado;
4. amostras sanitizadas de contrato;
5. matriz que relaciona cada métrica web aos eventos que a comprovam;
6. orçamento preliminar de eventos por segundo e armazenamento diário.

Somente após a aprovação desses seis artefatos deve começar a ingestão em
homologação. Custo de infraestrutura e operação permanece `unknown` até medir o
volume do corpus e escolher o ambiente.

## 21. Fora do escopo atual

- ativar o Agent por padrão ou transmitir a outbox;
- implementar API remota, worker, banco do servidor ou painel;
- alterar o decoder;
- criar DNS, firewall, domínio, contêiner ou volume;
- migrar dados reais;
- publicar executável ou site;
- controle remoto;
- automação, injeção, hook, OCR ou ação no jogo;
- remover funcionalidades da versão desktop;
- decidir antecipadamente Redis, Kafka ou microserviços.

## 22. Documentos relacionados

- `ANALISE-WEB-DEDICADA-RF-QOL-2.0.md` — análise anterior, ainda centrada em
  processamento local;
- `PLANO-RF-QOL-2.0.md` — estado da versão desktop preservada;
- `SPEC-SESSOES-LAN-RF-QOL-2.0.md` — alternativa LAN, não usada como servidor
  dedicado;
- `SPEC-LICENCA-RF-QOL-2.0.md` — features e lease v3;
- `SPEC-BANCO-PVE-STATUS-RF-QOL-2.0.md` — semântica atual do Banco PvE/status;
- `MONITORES-PVE-PVP-BOSS.md` — contratos atuais para equivalência em shadow
  mode.
