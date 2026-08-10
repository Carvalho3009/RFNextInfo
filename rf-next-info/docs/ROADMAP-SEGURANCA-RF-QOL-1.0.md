# Roadmap de segurança — RF QOL 1.0

Baseline: RF NEXT QOL 3.0.11 beta  
Branch de planejamento: `plan/rf-qol-security-1.0`  
Estado geral: implementação local isolada autorizada em 09 ago 2026;
publicação não autorizada

Identidade atual: produto/executáveis RF QOL com logo e identidade visual
Karvalho, conforme decisão posterior do owner em 09 ago 2026.

## Princípios de execução

- Cada fase termina em evidência verificável.
- Cliente, emissor e site mudam de forma compatível dentro da mesma RC.
- Nenhuma chave privada entra no repositório.
- Nenhuma mudança chega à beta publicada, produção ou release sem gate próprio.
- Rollback da implementação é por branch/worktree; rollback do produto é por
  instalador autenticado por manifesto Ed25519.
- Mudanças de segurança não são escondidas em alterações de marca ou interface.
- A revisão do Fable é complementar e não bloqueante. Se houver limite de
  sessão, HTTP 429, timeout ou indisponibilidade, registrar `sem resultado` e
  continuar com evidência local, documentação oficial e os gates do owner.

## Marcos

| Marco | Resultado | Estado | Gate |
|---|---|---|---|
| M0 | Baseline 3.0.11 e riscos confirmados | Concluído | — |
| M1 | SPEC e roadmap aprovados | Concluído | G0 |
| M2 | Lease v2, chaves e autorização central | Concluído localmente; produção pendente | G1 |
| M3 | Emissor/site v2 integrados | Concluído em staging isolado; produção pendente | G1 |
| M4 | Update/rollback/ACL seguros | Parcial: update/ACL prontos, rollback assinado pendente | G1 |
| M5 | Build rastreável e conteúdo assinado | Parcial: portátil/instalador/SBOM/procedência prontos, chave Ed25519 definitiva pendente | G2 |
| M6 | RC validada em ambiente real | Parcial: instalador validado localmente; matriz limpa pendente | G3 |
| M7 | Release RF QOL 1.0 | Pendente | G4 |

## Fase 0 — Baseline e proposta

Estado: concluída nesta branch de planejamento.

Entregas:

- confirmação da beta remota 3.0.11;
- worktree isolada no commit exato;
- regressão inicial com 182 testes aprovados e 23 ignorados;
- inventário de lacunas de confiança, licença, update e rollback;
- plano, SPEC e roadmap;
- revisão paralela Fable confrontada com a evidência local e documentação
  oficial atual.

Aceite:

- tree local igual à publicação remota;
- documentos sem afirmar implementação inexistente;
- nenhuma alteração na beta publicada.

G0 aprovado pelo owner em 09 ago 2026.

## Fase 1 — Cerimônia e contratos de segurança

Estado real: contrato, runbook e vetor público concluídos; lease definitiva
gerada, revisada e recuperável; kit de update validado, mas a geração da chave
definitiva continua pendente de execução física offline.

Objetivo: fechar os formatos antes do código.

Tarefas:

1. Localizar o repositório e o estado implantado do emissor de licença.
2. Congelar lease v2 e manifesto v2.
3. Gerar par Ed25519 de lease para uso online.
4. Gerar par Ed25519 separado de update para uso offline.
5. Definir `key_id`, custódia, backup, acesso e rotação.
6. Criar vetores públicos de teste válidos e inválidos, sem chaves privadas.
7. Registrar que executável e instalador não usam Authenticode e que a confiança
   do conteúdo vem do manifesto/procedência Ed25519 e dos hashes.
8. Congelar os nomes `RF QOL.exe` e `RF QOL Setup 1.0.0.exe` nos scripts de
   build, manifesto, atalhos, desinstalador e testes.

Critérios de aceite:

- duas chaves diferentes e papéis documentados;
- chave de update ausente do servidor e do repositório;
- vetores cobrem assinatura alterada, key role trocado, produto/audience errada,
  instalação errada e tempo inválido;
- processo de recuperação/rotação documentado.

Rollback:

- destruir pares ainda não implantados e repetir a cerimônia;
- nenhum cliente ou servidor existente é alterado nesta fase.

G1 aprovado para contratos, chaves de desenvolvimento e staging isolado. Chaves
definitivas continuam condicionadas à cerimônia própria.

## Fase 2 — Base de confiança e licença no cliente

Estado real: concluída na implementação local isolada. Lease v2, UUID de
instalação, prefixo RFQ, estados normativos, 24 h, recuo de relógio, DPAPI/ACL e
gates das duas interfaces possuem testes automatizados.

Objetivo: substituir confiança mutável por âncoras pinadas e aplicar 24 horas.

Tarefas:

1. Pinar as duas chaves públicas no código empacotado.
2. Remover qualquer uso de chave recebida da rede ou do estado local.
3. Implementar validação fechada de lease v2.
4. Criar máquina de estados de licença.
5. Aplicar teto local de 24 horas e guarda contra recuo de relógio.
6. Criar autorização compartilhada por capacidade.
7. Integrar o gate em captura, monitores, ingestão, leitura, exportação, envio,
   autoexportação, atalhos e interface legada.
8. Preservar ativação, suporte, Discord, diagnóstico local e update sem licença.
9. Criar estado protegido e ACL admin-only para licença/anti-rollback.
10. Assinar permissões `base`, `monitor-pve`, `monitor-pvp` e `monitor-boss`;
    manter PvE/PvP visíveis e bloqueados sem permissão e ocultar Boss.

Critérios de aceite:

- estado mutável não consegue substituir a chave pinada;
- lease v1 e licenças antigas são rejeitadas;
- boundary test de 24 horas passa;
- exportação direta pelo motor falha sem licença antes de criar arquivos;
- perda de licença encerra captura com preservação dos brutos;
- arquivos existentes não são apagados nem criptografados;
- regressão funcional completa continua verde.
- atalhos, overlays e chamadas diretas não contornam os gates dos módulos.

Rollback:

- reverter apenas a branch antes de integrar emissor/site;
- nenhuma nova licença é emitida até o cliente passar nos vetores.

## Fase 3 — Emissor e site

Estado real: concluído em staging isolado. O emissor Docker foi localizado,
evoluído numa worktree separada e integrado ao cliente/site por `/api/v2`.
Produção continua em `/api/v1` e não foi alterada.

Objetivo: emitir e impor lease v2 ponta a ponta.

Tarefas:

1. Criar namespace/produto novo `rf-qol`.
2. Emitir novas chaves de acesso e `installation_id` aleatório.
3. Assinar lease v2 com teto de 24 horas.
4. Implementar renovação, expiração e revogação.
5. Atualizar introspecção do site para v2.
6. Rejeitar lease antiga e product/audience/instalação divergentes.
7. Aplicar rate limit e auditoria sanitizada.
8. Validar que indisponibilidade não vira autorização no servidor.

Critérios de aceite:

- ativação -> renovação -> expiração -> revogação passa em staging;
- lease antiga falha no cliente e no site;
- upload com lease v2 válida é idempotente e aceito;
- upload expirado/revogado retorna erro fechado e auditável;
- nenhuma chave de acesso ou chave privada aparece em logs/backup de teste.

Evidência de staging em 09 ago 2026: ativação RFQ, validação pelo cliente,
renovação com novo `lease_id`, introspecção, diagnóstico sanitizado, bloqueio
por instalação divergente e revogação passaram no contêiner paralelo.

Rollback:

- manter produção antiga isolada;
- remover namespace v2 de staging sem tocar nas licenças antigas;
- as duas linhas não compartilham chaves nem banco lógico de autorização.

## Fase 4 — Update, anti-downgrade, ACL e rollback

Estado real: manifesto v2, hash/tamanho, anti-downgrade, staging admin-only e
reverificação foram implementados. O rollback inseguro foi
removido e permanece deliberadamente indisponível até existir um instalador
anterior coberto por manifesto Ed25519 e compatível; por isso a fase não está
concluída.

Objetivo: impedir execução de artefato não confiável.

Tarefas:

1. Implementar manifesto v2 e ferramenta offline de assinatura.
2. Validar product/channel/arquitetura/expiração/sequence/tamanho/SHA-256.
3. Persistir maior `release_sequence` em estado admin-only.
4. Mover staging para diretório admin-only.
5. Reverificar manifesto Ed25519, tamanho e SHA-256 imediatamente antes de abrir.
6. Informar que o instalador não usa assinatura de código do Windows.
7. Remover rollback por cópia de `RFNextInfo.exe`.
8. Implementar rollback por instalador anterior coberto por manifesto Ed25519.
9. Exigir declaração de compatibilidade do banco e backup verificável.
10. Auditar e corrigir ACLs do instalador.

Critérios de aceite:

- feed, manifesto e asset adulterados são rejeitados;
- sequence antigo é rejeitado no update normal;
- rollback explícito ignora somente sequence, mantendo assinatura Ed25519,
  tamanho, hash e compatibilidade;
- `icacls` prova que nenhum caminho executável é `users-modify`;
- corrida de substituição entre download e execução é detectada;
- captura/banco são encerrados de forma consistente antes do instalador;
- atualização continua disponível sem licença.

Rollback:

- reinstalar manualmente a última RC assinada compatível;
- restaurar backup somente quando o schema declarar compatibilidade.

## Fase 5 — Cadeia de build e procedência

Estado real: locks com hashes no cliente e emissor, imagem-base por digest,
SBOM, procedência, assinatura destacada, build portátil, NSIS 3.12, instalador
e self-tests concluídos. A chave offline definitiva de update permanece
externa; o gate de release a exige.

Objetivo: produzir artefato rastreável, embora deliberadamente sem Authenticode.

Tarefas:

1. Fechar dependências com versões e hashes.
2. Gerar SBOM.
3. Construir em ambiente limpo a partir de commit limpo.
4. Executar testes, self-test, scan de segredos e scanner de dados proibidos.
5. Confirmar `NotSigned` e registrar `authenticode=false` na procedência.
6. Calcular hashes sobre os bytes finais.
7. Gerar procedência/atestação do build.
8. Assinar o manifesto v2 por último, offline.

Critérios de aceite:

- lock com hashes é suficiente para reconstruir o ambiente;
- SBOM corresponde ao pacote;
- executável e instalador estão `NotSigned` conforme a decisão do owner;
- hashes, commit e ferramentas constam na procedência;
- scan não encontra segredo, token, ticket ou payload proibido;
- manifesto publicado corresponde byte a byte ao instalador final.

Rollback:

- descartar artefatos; código e produção não são afetados.

Gate: G2 para uso das chaves Ed25519 definitivas.

## Fase 6 — RC e validação real

Estado real: pacote e instalador locais gerados com Python 3.13; instalação,
autoteste e desinstalação passaram em destino isolado no Windows 11 atual.
Windows limpos 10/11, licença/chaves de produção e teste com dois clientes
seguem pendentes. Ativação, revogação e cutover passaram em staging.

Objetivo: provar o sistema fora do ambiente do implementador.

Matriz mínima:

- Windows 10 x64 limpo;
- Windows 11 x64 limpo;
- instalação e primeira execução;
- ativação com licença nova;
- online, offline abaixo de 24h e expiração no limite;
- recuo de relógio;
- revogação online;
- captura com até dois clientes;
- perda de licença durante captura;
- bloqueio de leitura/processamento/exportação/envio;
- preservação de brutos;
- update RC1 -> RC2;
- rollback RC2 -> RC1 compatível;
- inspeção de ACLs;
- comportamento do SmartScreen;
- link do Discord;
- scanner de arquivos/logs/banco/diagnóstico.

Critérios de aceite:

- todos os itens com evidência e responsável;
- nenhum P0/P1 aberto;
- validação executada por pessoa diferente do implementador;
- hashes finais registrados;
- rollback testado na instalação real.

Gate: G3 antes do teste real; G4 antes de publicar.

## Fase 7 — Release e operação

Objetivo: publicar somente o artefato aprovado.

Tarefas:

1. Publicar manifesto, instalador, hashes, SBOM e procedência.
2. Confirmar feed estável e download público.
3. Validar assinatura e hash do arquivo público, não apenas do arquivo local.
4. Monitorar ativação, validação, update e erros sem telemetria indevida.
5. Manter chave de update offline.
6. Preparar resposta a comprometimento das chaves de lease ou update.

Critérios de aceite:

- superfície pública devolve exatamente o artefato aprovado;
- instalação pública repete o self-test;
- servidor aceita apenas lease v2 do novo produto;
- release e produção são declaradas concluídas somente após validação pública.

## Estado dos gates

- G0 — aprovado em 09 ago 2026.
- G1 — aprovado para implementação e staging isolados.
- G2 — Authenticode removido do escopo pelo owner; lease definitiva concluída
  e kit de update validado; chave definitiva de update permanece pendente da
  cerimônia física offline.
- G3 — aprovado para RC e testes locais isolados.
- G4 — pendente; nenhuma publicação/release ou mudança de produção.

## Estado de custo e rollback

- Custo real adicional desta decisão: zero; nenhum certificado será comprado.
- Rollback da etapa atual: remover a worktree/branch de planejamento; a beta
  publicada permanece intacta.
