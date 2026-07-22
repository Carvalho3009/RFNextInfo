# Auditoria — DOCUMENTO_TECNICO_COMPLETO_PROJETOS.md (doc consolidado multi-projetos)

**Data:** 2026-07-22
**Método:** cruzamento do doc com (a) a auditoria já feita do repo Site, (b) o registro de projetos e a memória compartilhada do MCP_CASA (K:\MCP), e (c) sondagem de diretórios no seu PC. As pastas `K:\MCP\*` não estão conectadas a esta sessão, então arquivos individuais lá não foram lidos — a verificação usou o registro de projetos, as memórias de handoff de 22/07 e a estrutura de pastas confirmada.

---

## 1) Veredito

O doc consolidado é um **retrato razoável, mas já desatualizado no dia em que foi escrito** — e o ponto mais grave é que ele **contradiz a política de consolidação registrada no próprio MCP em 22/07/2026**: o handoff oficial definiu `K:\MCP\projects\<slug>` como raiz canônica dos 7 projetos e rebaixou as pastas do OneDrive (`RF NEXt`, `ROOC AM`, `Poke Idle`, `Poke`) a **histórico, sem consolidação**. O doc, porém, aponta o OneDrive como caminho principal do RF Next e cita as cópias OneDrive como fontes técnicas vivas.

## 2) Confirmações (o que confere)

- **K:\MCP existe com a estrutura descrita**: `control`, `host-worker`, `local-ai-mcp`, `projects`, `stack`, `tools`, `workspace` — confirmado por sondagem de diretório.
- **`K:\MCP\projects` contém exatamente**: `aion2-global`, `controlar-tela`, `painel-v2`, `pokeidle`, `RF Kojiro`, `rf-next`, `rooc-americas` — e todos os 7 estão cadastrados no registro de projetos do stack.
- **Poke Idle (§5)**: canônico em `K:\MCP\projects\pokeidle` (com .git, Dockerfile e docker-compose) e OneDrive como histórico — exatamente como o doc recomenda na matriz de riscos. Confere com o handoff.
- **ROOC AM (§2)**: caminho canônico `K:\MCP\projects\rooc-americas` confere; a duplicidade com o OneDrive é real e o doc a sinaliza corretamente como risco.
- **Site (§3)**: descrição compatível com a auditoria detalhada já entregue (compose como padrão, projects/ embutido).

## 3) Divergências e erros factuais

| # | Achado | Evidência |
|---|---|---|
| E1 | **RF Next com caminho principal errado**: §1 aponta `C:\...\OneDrive\Documentos\RF NEXt` como caminho principal. O handoff de 22/07 define `K:\MCP\projects\rf-next` como canônico e o OneDrive como histórico. | Handoff consolidado 22/07 (memória MCP id 126) |
| E2 | **§4 descreve um RF Next que não é mais o projeto ativo**: o doc só fala de captura de tráfego (ADB/tcpdump/PCAP). O trabalho ativo do rf-next é a **Calculadora** (farm MVP, Craft e Codex entregues em 22/07, spec-driven, em `K:\MCP\projects\rf-next\calc\`), que o doc nem menciona. | Memórias MCP ids 132, 141, 142 |
| E3 | **Caminhos com typo em §4.2** — inutilizáveis para copy-paste: `...\OneDrive\Documents\RF NEXt\...` ("Documents" em vez de "Documentos") e `C:\Users\cel3c\...` (duas ocorrências; o usuário é `celc3`). | Doc, linhas 96–98 |
| E4 | **Controlar tela com release desatualizada**: doc cita `release-upload-v1.1.0\ControlarTela.exe` no OneDrive. O artefato real registrado em 22/07 é `bin\Release\Ronaldinho-Protecao-v1.3.0-win-x64.zip` no repo canônico `K:\MCP\projects\controlar-tela` (com .git, atualizado 21/07). | Memória MCP id 121 |
| E5 | **§7 (MCP) diz que tudo sobe por Docker Compose** — mas o `local-ai-mcp` (que o doc chama de "serviço principal") roda **nativo no Windows, porta 8000**, fora do compose; no Docker ficam Postgres, control-api (`mcp-control`, 127.0.0.1:8080) e socket-proxy, com host-worker executando comandos do host via allowlist. | Memórias MCP ids 2, 51, 117 |
| E6 | **§3.4 "cada projeto embutido mantém seu próprio Dockerfile"** — dentro de `Site/projects/` só `rf-next` tem Dockerfile (e o compose nem o usa; builda de `../RF NEXt`). `palworld-mods` não tem stack próprio. | Auditoria anterior do Site |

## 4) Omissões relevantes

- **4 projetos ativos fora do doc**: `aion2-global` (guia AION 2 Global), `painel-v2` (rework do painel MCP com identidade Karvalho), `rf-kojiro` (RF Data Studio/Editor — projeto distinto do rf-next) e `game-data-monitor`. O doc lista 6 projetos; o ecossistema registrado tem mais — além do **Karvalho Gacha (Unity)** e do stack de mídia citados nas instruções permanentes.
- **MCP público não aparece**: `mcp.karvalho.dev.br` é servido via **o túnel Cloudflare do Site** (Service `http://host.docker.internal:8000`, `httpHostHeader=127.0.0.1:8000`). Essa é uma dependência crítica **Site → MCP** que falta no mapa do §8: se o `cloudflared` do Site cair, o MCP público cai junto.
- **Automação ativa não documentada**: a tarefa `atualizar-guia-rooc-a-cada-6h` roda `build-rooc-content.ps1` + `check-rooc-site.ps1` a cada 6h quando os markdowns mudam. Relevante para quem assume: mudanças no pipeline têm efeito automático.
- **A ponte Site ⇄ rf-next real**: `Site\projects\rf-next` recebeu em 22/07 uma **cópia de deploy** (`craft.html`, servida em `rfexp.karvalho.dev.br/craft.html` pelo `server.py`). Ou seja, não é pasta órfã (como parecia na auditoria anterior) — é **alvo de deploy** dos entregáveis do rf-next canônico. Nenhum dos dois documentos descreve esse fluxo.
- **Pipeline editorial do Site consome a cópia "histórica"**: `build-rooc-content.ps1` lê de `..\ROOC AM\conteudo` (OneDrive) — a pasta que o handoff rebaixou a histórico. A publicação do site ROOC, portanto, **não** sai do canônico `K:\MCP\projects\rooc-americas`. Contradição operacional real entre a política de consolidação e o pipeline em produção.
- **Contexto de calendário**: abertura prevista do ROOC Americas em **23/07/2026** (amanhã) com política editorial pré-OBT ("[VALIDAR NA ABERTURA]") — nada disso está no doc, e é o evento operacional mais próximo.

## 5) Questão aberta que continua sem resposta (agora mais precisa)

O compose do Site builda `rf-next-calculadora:local` de **`../RF NEXt` (OneDrive, agora "histórico")**, enquanto os entregáveis novos da calculadora nascem em **`K:\MCP\projects\rf-next`** e uma cópia de deploy é posta em **`Site\projects\rf-next`** — que o compose não monta nem builda. Como a cópia de deploy chega ao container em execução? Hipóteses: o Dockerfile de `../RF NEXt` copia de `Site\projects\rf-next`; ou o deploy exige rebuild manual; ou há passo manual não registrado. **Precisa ser respondido por você (ou auditando `../RF NEXt`) antes de qualquer mudança no rfexp.**

## 6) Recomendações específicas para este doc

1. Corrigir caminhos (E1, E3, E4) e registrar `K:\MCP\projects\<slug>` como caminho principal de TODOS os projetos, com OneDrive marcado explicitamente como "histórico — não editar".
2. Reescrever §4 em duas partes: "RF Next — pesquisa/captura (histórico, OneDrive)" e "rf-next — Calculadora (ativo, K:\MCP)"; incluir rf-kojiro como projeto separado.
3. Adicionar ao §8: Site⇄MCP (túnel), Site⇄rf-next (deploy copy + build `../RF NEXt`), automação 6h do ROOC.
4. Incluir os projetos ausentes (aion2-global, painel-v2, rf-kojiro, game-data-monitor, Karvalho Gacha) ou declarar explicitamente o escopo como parcial.
5. Depois das correções, este doc e o `DOCUMENTO_TECNICO.md` do Site deveriam referenciar um ao outro — hoje eles se contradizem sobre o rf-next sem se citarem.

---
*Auditoria com verificação via registro de projetos e memória compartilhada do MCP_CASA + sondagem de diretórios. Arquivos dentro de K:\MCP não foram lidos individualmente (pasta não conectada à sessão) — uma auditoria profunda desses repos requer conexão da pasta.*
