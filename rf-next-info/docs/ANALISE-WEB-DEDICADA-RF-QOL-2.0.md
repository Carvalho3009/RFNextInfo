# Análise de arquitetura web dedicada — RF QOL 2.0

Data: 20 ago 2026  
Estado: planejamento  
Escopo: site/servidor dedicado para receber e apresentar informações do RF QOL  
Não autoriza: implementação, migração de banco, abertura de rede, deploy, publicação ou geração de instalador

## 1. Definição de “web based” neste projeto

Nesta proposta, **web based não significa executar o RF QOL em um navegador
local**.

O programa Windows continua instalado em cada computador e permanece responsável
por:

- captura passiva por Pktmon;
- decodificação e sanitização dos eventos;
- estado em tempo real de cada cliente;
- overlays, alarmes e sons;
- funcionamento offline e armazenamento temporário;
- controle local de iniciar, pausar e encerrar a leitura.

Um site/servidor dedicado passa a receber projeções sanitizadas e autenticadas
para centralizar:

- computadores e clientes vinculados ao Profile;
- sessões ativas e concluídas;
- EXP, nível, tempo, recursos e combate;
- mapa, região e posição, conforme a política de privacidade aprovada;
- drops, ranking de EXP e observações dos bancos permitidos;
- Boss, incluindo dano acumulado e separação por jogador e guilda;
- relatórios e históricos acessíveis de qualquer dispositivo autorizado.

## 2. Resultado recomendado

Adotar uma arquitetura híbrida:

```text
Cliente do jogo
      |
      v
RF QOL Agent no Windows
captura -> decoder único -> estado sanitizado
      |                         |
      |                         +-> UI, overlays e sons locais
      |
      +-> fila limitada em disco -> HTTPS autenticado -> servidor RF QOL
                                                        |
                                                        +-> banco central
                                                        +-> processamento
                                                        +-> API de consulta
                                                        +-> painel web
```

O **RF QOL Agent** não deve ser substituído por um navegador. A migração consiste
em transformar a integração atual com o site em um canal contínuo, resiliente e
versionado, sem criar um segundo capturador ou decoder.

## 3. O que já pode ser reaproveitado

A base atual já possui elementos importantes para essa evolução:

- captura passiva e decoder único;
- stream e redutores de estado usados pelos monitores;
- armazenamento local e checkpoints de sessão;
- autenticação por Profile;
- cliente de integração com o site;
- chaves de idempotência para evitar importações duplicadas;
- envios de Mercado, Farm/subsessão, observações, Banco PvE e ranking de EXP;
- API local limitada a `127.0.0.1` para saídas locais sanitizadas.

Consequência: a versão web dedicada deve **ampliar a sincronização existente**,
não reescrever a leitura do protocolo nem transformar a API local em servidor de
internet.

As rotas atuais de importação devem continuar compatíveis durante a migração.
Um contrato novo e unificado pode ser introduzido de forma aditiva, enquanto os
envios antigos são desativados somente depois de equivalência e rollback
comprovados.

## 4. Responsabilidades por componente

### 4.1 Programa Windows

- captura e decodifica localmente;
- mantém somente as janelas recentes necessárias em RAM;
- transforma eventos em projeções permitidas;
- agrupa eventos em lotes idempotentes;
- persiste a fila offline em disco, com tamanho e prazo limitados;
- reenvia lotes após falhas usando espera progressiva;
- recebe confirmações por lote ou registro;
- mantém overlays e alertas funcionando mesmo sem internet;
- nunca depende da resposta do site para reconhecer Farm, PvP, Boss ou Teleporte.

### 4.2 Servidor de ingestão RF QOL

- autentica Profile, instalação e versão do protocolo de envio;
- valida tamanho, schema, assinatura, horário e idempotência;
- rejeita campos proibidos;
- grava o lote antes de confirmá-lo;
- atualiza o estado vivo de computador, cliente e sessão;
- encaminha históricos para processamento assíncrono quando necessário;
- aplica limites por instalação e Profile;
- produz auditoria sanitizada, sem payload bruto ou segredo.

### 4.3 Banco central

Separar logicamente:

- identidade de Profile, instalação e cliente público;
- estado vivo substituível;
- sessões e checkpoints;
- eventos históricos autorizados;
- ranking de EXP e suas capturas;
- catálogo compartilhado de mapas e Banco PvE;
- drops e Boss;
- recibos de idempotência e auditoria.

O banco de ingestão de alto volume não deve compartilhar indefinidamente as
mesmas tabelas de conteúdo editorial do site. A separação pode começar por
schemas e limites próprios; serviço ou banco físico separado deve ser adotado
quando volume, manutenção ou disponibilidade justificarem.

### 4.4 Painel web

Primeira entrega somente leitura, com:

- computadores online, offline e última atualização;
- clientes observados em cada computador;
- sessão ativa por cliente;
- EXP, nível, percentual, tempo, recursos e combate;
- status atual com idade da informação;
- histórico de sessões concluídas;
- indicação explícita de dado atual, atrasado ou indisponível.

O painel não inicia, pausa, encerra ou configura o programa nesta fase.

## 5. Identidade e modelo de acesso

Usar duas identidades complementares:

1. **Profile:** define o usuário e quais dados ele pode consultar ou
   compartilhar.
2. **Instalação:** identifica criptograficamente cada RF QOL Agent autorizado a
   enviar dados para aquele Profile.

Recomendação:

- criar um par criptográfico por instalação;
- proteger a chave privada local com DPAPI;
- registrar somente chave pública, identificador opaco e metadados mínimos;
- assinar cada lote ou usar um desafio curto emitido pelo servidor;
- manter o token de Profile protegido e nunca registrá-lo em logs;
- permitir revogação individual de uma instalação;
- tratar licença como liberação de módulos, não como a única autenticação da
  transmissão.

Por padrão, os dados devem ser privados para o Profile. Compartilhamento com
guilda ou público deve ser opt-in, por domínio de dados, com revogação e
auditoria.

## 6. Contrato de envio proposto

Introduzir um envelope versionado, por exemplo `rf-qol.ingest-batch/v1`:

```json
{
  "schema": "rf-qol.ingest-batch/v1",
  "batch_id": "identificador-opaco-idempotente",
  "installation_id": "identificador-publico-da-instalacao",
  "sent_at": "2026-08-20T18:00:00Z",
  "events": [
    {
      "type": "session.checkpoint",
      "occurred_at": "2026-08-20T17:59:58Z",
      "client_id": "identificador-publico-do-cliente",
      "payload": {}
    }
  ]
}
```

Rota candidata:

```text
POST /api/qol/v1/ingest/batches
```

Rotas especializadas podem existir para checkpoint ou finalização, mas devem
usar o mesmo envelope, autenticação e idempotência:

```text
POST /api/qol/v1/sessions/checkpoint
POST /api/qol/v1/sessions/finalize
```

Resposta mínima:

```json
{
  "batch_id": "identificador-opaco-idempotente",
  "accepted": true,
  "accepted_events": 1,
  "rejected_events": [],
  "received_at": "2026-08-20T18:00:01Z"
}
```

Cada evento deve possuir schema próprio. Campos desconhecidos são rejeitados ou
ignorados conforme a versão declarada; nunca interpretados por heurística.

## 7. Tipos de informação e frequência inicial

| Informação | Frequência recomendada | Regra |
|---|---:|---|
| Presença do computador/cliente | 5 s | Atualiza estado vivo; não cria histórico a cada envio. |
| Status e sessão ativa | 5 s | Enviar somente mudança ou checkpoint compacto. |
| EXP, nível, recursos e combate | 10 s | Checkpoint substituível durante a sessão. |
| Mapa, região e posição | 5 s | Privado por padrão; posição não vira histórico permanente automaticamente. |
| Eventos de drop e Boss | lote de 1 a 5 s | Preservar horário e cliente; confirmar por evento. |
| Banco PvE e conhecimento | quando mudar | Não reenviar monstro/local já confirmado. |
| Ranking Top 100 | ao concluir captura válida | Snapshot parcial continua local. |
| Finalização de sessão | imediata | Prioridade alta e idempotência obrigatória. |

Esses valores são ponto de partida para homologação. O servidor pode recomendar
intervalos maiores sob carga, mas nunca deve alterar silenciosamente a semântica
local dos monitores.

## 8. Dados permitidos e proibidos

### Permitidos, conforme feature e privacidade

- identificadores públicos e opacos de instalação, cliente e sessão;
- nome do personagem, servidor, nível e EXP;
- duração, recursos e métricas de combate sanitizadas;
- mapa, região e coordenadas do próprio personagem;
- jogadores próximos somente se houver política aprovada;
- nome, nível e HP máximo de mobs;
- drops confirmados pelo evento de recompensa;
- dano de Boss acumulado por jogador e guilda;
- snapshots completos do ranking Top 100;
- horários, versão do schema, confiança e origem da evidência.

### Proibidos

- pacotes, fluxos ou payloads brutos;
- arquivos ETL, PCAP ou PCAPNG;
- portas efêmeras como identidade;
- token, ticket, senha, credencial ou chave privada;
- payload ou conteúdo do opcode `0x0101`;
- identificadores internos do jogo sem necessidade e aprovação;
- caminhos locais, traceback ou detalhes de ambiente em erros remotos.

O programa deve construir o payload por lista positiva de campos. Não deve
serializar diretamente objetos internos do decoder.

## 9. Memória, fila offline e uso de disco

A sincronização com o site não pode recriar o crescimento de memória observado
em sessões longas.

Regras obrigatórias:

- fila de envio em RAM pequena e limitada;
- lotes pendentes persistidos em SQLite ou spool equivalente no disco;
- confirmação remove ou compacta o lote sem manter cópia residente;
- consultas do painel nunca carregam todo o histórico no programa;
- uma fila por instalação, com `client_id` em cada evento, sem uma thread por
  cliente;
- tamanho máximo do lote e quantidade máxima de lotes em voo;
- descarte por prioridade somente para estado efêmero substituível;
- sessão finalizada, ranking completo, drops confirmados e eventos de Boss não
  podem desaparecer silenciosamente;
- o limite de RAM escolhido pelo usuário também limita cache, serialização e
  concorrência da sincronização;
- o uso do disco, prazo offline e política de compactação ficam visíveis nas
  configurações.

Ordem de adaptação sob pressão de memória:

1. reduzir cache de documentos já serializados;
2. compactar estados vivos repetidos;
3. aumentar o intervalo de checkpoints substituíveis;
4. reduzir a quantidade de lotes simultâneos;
5. preservar eventos duráveis no disco e liberar suas cópias em RAM.

O sistema não deve resolver pressão de memória apagando campos de um evento já
aceito nem mantendo todo o histórico offline em uma coleção Python/Qt.

## 10. Funcionamento offline

Quando o servidor estiver indisponível:

- captura, monitores, overlays e sons continuam locais;
- o site mostra a última atualização como atrasada, nunca como estado atual;
- o Agent grava somente lotes autorizados e limitados;
- tentativas usam espera progressiva com variação aleatória;
- abrir o programa pode antecipar uma tentativa, sem bloquear a interface;
- a reconexão envia primeiro finalizações e eventos duráveis, depois estados
  substituíveis;
- o servidor reconhece reenvio pelo `batch_id` e não duplica contadores.

Ao atingir o limite offline, estados efêmeros antigos podem ser substituídos
pelo snapshot mais recente. O tratamento de históricos duráveis depende de uma
política de retenção aprovada antes da implementação.

## 11. Múltiplos computadores e clientes externos

O servidor dedicado passa a ser o ponto de encontro entre computadores do mesmo
Profile, sem exigir que um computador abra porta na rede local.

Fluxo recomendado:

1. cada instalação envia sua lista sanitizada de clientes e sessões;
2. o site mostra todas as instalações autorizadas;
3. o programa pode consultar no servidor os clientes externos disponíveis;
4. **Adicionar cliente** oferece local, emulador ou externo via API;
5. o cartão externo é somente leitura e recebe o selo de origem;
6. remover o cartão não apaga a sessão nem revoga a instalação remota.

No primeiro ciclo, o programa externo consulta estado pelo site usando
requisições periódicas e cache limitado. WebSocket pode ser avaliado depois de
medir volume e necessidade; não é requisito do MVP.

A especificação LAN permanece independente. A arquitetura dedicada não deve
ser implementada alterando o bind da API local de `127.0.0.1`.

## 12. Site e infraestrutura recomendados

Separar visualmente o produto dentro do ecossistema Karvalho:

- `qol.karvalho.dev.br`: painel web;
- `api-qol.karvalho.dev.br`: ingestão e consulta do RF QOL.

Os nomes são recomendações, não destinos aprovados.

Para a primeira fase, usar a solução mais simples que preserve isolamento:

- API HTTPS;
- banco transacional com índices por Profile, instalação, cliente e tempo;
- worker para consolidações que não precisam responder no upload;
- armazenamento de estado vivo separado logicamente do histórico;
- métricas de filas, latência, rejeição, duplicidade e crescimento do banco;
- backup, migração aditiva e rollback antes de produção.

Uma fila externa ou múltiplos microserviços só devem ser adicionados quando
medição de volume ou disponibilidade provar a necessidade.

## 13. Migração por fases

### Fase 0 — decisões e contratos

- aprovar dados enviados, retenção e compartilhamento;
- definir schemas e limites;
- definir identidade da instalação e revogação;
- criar amostras sanitizadas e testes de contrato;
- manter todo envio novo desligado.

### Fase 1 — primeiro corte vertical

- registrar instalação e clientes;
- enviar presença e sessão ativa;
- enviar EXP, nível, tempo, recursos e combate;
- exibir computadores, clientes e sessão ativa no painel;
- manter o painel somente leitura.

Essa fase entrega o objetivo principal com o menor risco.

### Fase 2 — histórico e clientes externos

- finalizar e consultar sessões;
- mostrar histórico paginado;
- permitir que o programa adicione cliente externo via servidor;
- validar offline, duplicidade e isolamento entre Profiles.

### Fase 3 — domínios especializados

- mapa e região;
- drops e histórico;
- Boss acumulado por jogador e guilda;
- Banco PvE;
- ranking Top 100 e histórico de evolução.

Cada domínio recebe contrato, retenção e permissão próprios.

### Fase 4 — escala e operação

- ensaios prolongados de memória e tráfego;
- limites por Profile e instalação;
- observabilidade e alertas operacionais;
- backup/restauração;
- homologação com múltiplos computadores;
- migração gradual dos contratos antigos.

### Fase futura — comandos remotos

Somente após autorização específica, ameaça modelada e auditoria:

- iniciar ou pausar monitor;
- encerrar sessão;
- alterar configurações permitidas.

Comandos remotos não fazem parte da 2.0 inicial e não devem compartilhar o
mesmo escopo de autorização de leitura.

## 14. Gates necessários antes de implementar

1. **Escopo do MVP:** confirmar painel somente leitura com computadores,
   clientes e sessão ativa.
2. **Privacidade:** decidir se mapa, coordenadas e nomes próximos saem do PC.
3. **Compartilhamento:** privado por padrão; definir se haverá visão de guilda.
4. **Retenção:** definir prazos para estado vivo, sessões, drops, Boss, mapa e
   ranking.
5. **Identidade:** aprovar Profile + chave por instalação protegida por DPAPI.
6. **Infraestrutura:** aprovar host, domínio, banco, backup e ambiente de
   homologação.
7. **Recursos:** aprovar limites de RAM, disco, lote e prazo offline por perfil.
8. **Compatibilidade:** definir quanto tempo as rotas atuais permanecem ativas.
9. **Operação:** aprovar staging, ensaio real, deploy e rollback separadamente.
10. **Controle remoto:** manter bloqueado até autorização específica futura.

## 15. Critérios de aceite do MVP

- cada instalação só envia para o Profile autorizado;
- dois computadores do mesmo Profile aparecem separadamente;
- clientes não se misturam em sessão, drops, mapa ou combate;
- painel diferencia online, atrasado e offline;
- reenvio do mesmo lote não duplica métricas;
- perda de internet não interrompe monitores locais;
- fila offline respeita limites de RAM e disco;
- nenhum payload proibido aparece em envio, banco, resposta ou log;
- revogar uma instalação impede novos envios e consultas;
- programa antigo continua funcionando durante a migração;
- testes específicos e regressão completa passam antes do instalador;
- ensaio prolongado comprova estabilidade de memória no executável candidato.

## 16. Fora do escopo desta análise

- substituir captura passiva por hook, OCR ou automação do jogo;
- enviar pacotes brutos para decodificação no servidor;
- abrir a API local diretamente para a internet;
- controle remoto na primeira entrega;
- Banco de PvP e Banco de Leilão, mantidos para a 2.1;
- deploy, compra de infraestrutura, DNS, firewall ou publicação;
- validações manuais antes do executável candidato.

## 17. Recomendação final

Começar pelo corte vertical de **computadores + clientes + sessão ativa + EXP,
nível, tempo, recursos e combate**, com envio HTTPS de saída, fila offline
limitada e painel somente leitura.

Esse caminho aproveita a integração existente, atende ao objetivo de consultar
sessões de outros computadores e permite validar segurança, memória e volume
antes de enviar mapas, proximidade, drops e dados de Boss em escala.

## 18. Documentos relacionados

- `PLANO-RF-QOL-2.0.md` — plano geral e estado da versão 2.0;
- `SPEC-SESSOES-LAN-RF-QOL-2.0.md` — consulta direta entre computadores na
  rede local, independente desta proposta;
- `SPEC-LICENCA-RF-QOL-2.0.md` — módulos e licença da versão 2.0;
- `SPEC-MODULO-MAPA-RF-QOL-2.0.md` — contrato local de mapa e proximidade;
- `SPEC-BANCO-PVE-STATUS-RF-QOL-2.0.md` — Banco PvE e status do programa;
- `SPEC-RANKING-EXP-TOP100-RF-QOL-2.0.md` — ranking do servidor e histórico.
