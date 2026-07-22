# Relatório de Auditoria — Plataforma Karvalho (Doc vs. Repo)

**Data:** 2026-07-22
**Escopo:** `DOCUMENTO_TECNICO.md` auditado contra o estado real de `C:\Users\celc3\OneDrive\Documentos\Site` (compose, Caddy, Authentik, scripts, frontend, RF Next).
**Método:** 3 agentes de auditoria em paralelo (infra, frontend/conteúdo, scripts/segurança) + revisão e verificação cruzada dos achados críticos contra os arquivos reais.

---

## 1) Sumário executivo

O documento técnico é **majoritariamente fiel** ao repositório: versões de imagem, roteamento por host, volumes, encadeamento de identidade (Authentik → gateway → `X-Karvalho-User`) e o pipeline editorial conferem. Dá para confiar nele como mapa geral.

Porém, para **assumir o projeto** há 4 pontos que mudam decisões e precisam ser resolvidos primeiro:

1. **O repositório não tem versionamento real** — git em `master` com **zero commits e nenhum remote**. Todo o projeto vive só no disco/OneDrive.
2. **`infra/users.caddy` + `tools/manage-user.ps1` são um mecanismo morto** — nenhuma rota do Caddyfile consome esse arquivo; toda a autenticação real é `forward_auth` → Authentik. O doc apresenta o script como parte funcional do fluxo de acesso.
3. **Existem duas cópias do RF Next** — o compose builda de `../RF NEXt` (fora do repo, não auditável), mas há uma implementação completa e órfã em `projects/rf-next/` que o doc nunca menciona. Ambiguidade de fonte da verdade.
4. **A integração MCP Vision é declarada mas não comprovada** — o código disponível do RF Next não usa `MCP_VISION_*`; as variáveis podem estar mortas ou usadas só na versão externa.

---

## 2) O que confere (pode confiar no doc)

- **Stack compose**: `caddy:2-alpine` (gateway/portal/rooc), `postgres:16-alpine`, `goauthentik/server:2026.5.5` (server+worker), `cloudflared` sob profile `tunnel`; bind exclusivo `127.0.0.1:8088:80` no gateway; nenhum outro serviço expõe porta.
- **Volumes**: `rfnext-data:/data`, `authentik-database`, `authentik-data` — exatamente como documentado.
- **Roteamento**: `ragnarok.*` → rooc (com forward_auth + CSP restrita), `rfexp.*` → rfnext (forward_auth + injeção de `X-Karvalho-User`), `auth.*` → authentik-server:9000, portal público em `localhost`/`karvalho.dev.br`.
- **Cadeia de identidade**: `server.py` lê `X-Karvalho-User` (regex-normalizado), que o Caddyfile injeta de `X-Authentik-Username`. Coerente e correto. Bônus não documentado: o gateway remove `Cf-Access-Authenticated-User-Email` do request (anti-spoofing).
- **Segurança de segredos no git**: `.gitignore` cobre `.env`, `infra/authentik.env`, `infra/users.caddy`; os arquivos sensíveis existem localmente e estão fora do VCS.
- **Scripts Authentik**: `setup-authentik.ps1` gera env sem vazar segredo (e recusa sobrescrever); `new-authentik-invitation.ps1` cria convite single-use com validade padrão 30 dias (e apaga o convite anterior do mesmo usuário).
- **Pipeline editorial**: `build-rooc-content.ps1` converte os 6 markdowns de `..\..\ROOC AM\conteudo` (relativo a `tools/`), reescreve links `.md`→`.html`, injeta header/footer, TOC e paginação; `check-rooc-site.ps1` valida as 7 páginas, links/âncoras (inclusive cross-page), quiz e checklist. Nenhum link `.md` residual nas páginas geradas.
- **`script.js` do ROOC**: filtro de 14 classes, quiz com pontuação, checklist multi-perfil com localStorage, menu mobile — tudo implementado como descrito.
- **Portal**: HTML/CSS puro, sem script, só `/shared/styles.css` — como afirmado. Todas as imagens referenciadas existem em `web/assets/`.
- **SQL do RF Next**: 100% parametrizado (sem SQL injection); rotas limitadas a `/api/state`, `/api/history/general` e fallback SPA.

---

## 3) Divergências (doc diz X, repo mostra Y)

| # | Divergência | Evidência | Impacto |
|---|---|---|---|
| D1 | Doc §7 trata `users.caddy`/`manage-user.ps1` como camada de acesso ativa. **Nenhuma rota do Caddyfile referencia o arquivo** (só `import project_auth` → forward_auth Authentik; zero `basic_auth`). O script gera hash, valida e reinicia o gateway — sem efeito algum. | `infra/Caddyfile` (62 linhas, sem basicauth); `manage-user.ps1:29-45` | Alto — falsa sensação de controle de acesso; checklist §13 "testar 4 caminhos" não cobre isso |
| D2 | Doc §3/§12 diz que rfnext builda de `../RF NEXt` (confere no `compose.yml:36`), mas **omite que `projects/rf-next/` dentro do repo contém uma implementação completa** (Dockerfile, `server.py`, `index.html` de 826 linhas) não referenciada por nada. | `compose.yml:36-37`; `projects/rf-next/*` | Alto — duas fontes da verdade; risco de drift silencioso |
| D3 | Doc usa `MCP_VISION_TOKEN` (§3) e `RFNEXT_VISION_TOKEN` (§8) como se fossem a mesma coisa, sem explicar o mapeamento real: `MCP_VISION_TOKEN: ${RFNEXT_VISION_TOKEN:-}` — o nome no container difere do nome no `.env`. E o `.env.example` **não tem** linha para `RFNEXT_VISION_TOKEN`. | `compose.yml:41`; `.env.example` | Médio — operador preenche a variável errada e a integração falha em silêncio |
| D4 | Diagrama §2 mostra RF Next consumindo MCP Vision. O código disponível (`projects/rf-next/server.py` e `index.html`) **não referencia `MCP_VISION_*` em lugar nenhum** — só `RFNEXT_DB` e `RFNEXT_SELF_TEST`. | grep completo em `projects/rf-next/` | Médio — arquitetura declarada não comprovável; só a versão externa `../RF NEXt` poderia confirmar |
| D5 | Doc §11 lista CSP entre os "headers padrão". CSP **não está no bloco global** — é por rota, e a rota `auth.*` não tem CSP nenhuma. | `Caddyfile:19-25` (global), `:30,37,52` (por rota), `:56-59` (auth sem CSP) | Baixo/Médio |
| D6 | Doc §7 descreve só o fluxo de primeiro acesso. O blueprint define **também um fluxo de recuperação de senha** (`karvalho-password-recovery`, com `never_create` — correto, mas não documentado). | `karvalho-first-access.yaml:15-23,90-95` | Baixo |
| D7 | Doc §6 chama `check-rooc-site.ps1` de validação de "acessibilidade". O script checa presença de strings/atributos (`<main`, âncoras, checklist) — **não faz auditoria de acessibilidade real** (ARIA, alt, contraste, foco). | `check-rooc-site.ps1` | Baixo |

## 4) Omissões relevantes do documento

- **`web/assets/`** — a pasta mais importante do frontend (logos, hero, bestiário, emblemas — 7 PNGs, ~10 MB) não aparece na estrutura de `web` do §5, apesar de o `Site.Caddyfile` servir `/assets/*` e todas as páginas dependerem dela. (`guide-triptych.png` não é referenciado por nenhuma página — asset órfão.)
- **Pastas inteiras fora do doc**: `brand/` (kit de marca + manual PDF), `design/`, `output/` (brand kit zipado), `projects/palworld-mods/` (conteúdo sem relação com a plataforma, dentro do mesmo repo).
- **Duplicação de design tokens**: `brand/tokens/karvalho-colors.css` define as cores da marca, mas `web/shared/styles.css` e `web/rooc-am/styles.css` duplicam os hex manualmente sem importar o token — duas fontes de verdade para cor.
- **`authentik-worker` roda como `user: root`** (`compose.yml:83`).
- **Convite hardcoded**: `new-authentik-invitation.ps1` depende do admin `carvalho` existir e do slug `projetos-karvalho` no Authentik — se qualquer um mudar, o script quebra sem validação.
- **Política de senha mais fraca do que parece**: além do mínimo (8 chars, 1 minúscula, 1 dígito), `check_zxcvbn: false` e `check_have_i_been_pwned: false` — `aaaaaaa1` passa.
- **Observabilidade mínima**: só o Postgres tem healthcheck; gateway, portal, rooc, rfnext, server e worker não têm nenhum.
- **`RFNEXT_SELF_TEST=1`** (self-test embutido no `server.py`) não documentado.
- **Checklist §13 não inclui backup de `rfnext-data`** — justamente o volume com dados de usuários (SQLite).
- Detalhes menores: remoção do header `Server`, `trusted_proxies private_ranges`, os 5 headers `X-Authentik-*` copiados (doc cita só 1), `shm_size: 512mb`, montagem de blueprints `:ro`, hosts do PokeIdle (que na verdade **está atrás de forward_auth**, não é só "placeholder").

## 5) Riscos para quem assume o projeto (por severidade)

**Críticos**
1. **Zero commits, zero remote** — não existe histórico nem backup versionado de nada (nem infra, nem scripts, nem conteúdo). Qualquer corrupção/exclusão local é perda definitiva. O doc §12 não lista isso.
2. **Dependência de `../RF NEXt` não versionada e invisível** — se a pasta externa não existir, `docker compose up` falha por inteiro (o `gateway` tem `depends_on: rfnext`). E não há como auditar o que essa imagem contém.

**Altos**
3. **Mecanismo morto de autenticação** (D1) — além de confundir, o restart do gateway pelo `manage-user.ps1` é operação de risco sem benefício.
4. **Segredos sincronizados pelo OneDrive** — `.gitignore` protege do git, mas `infra/authentik.env` e `infra/users.caddy` estão dentro de uma pasta OneDrive, ou seja, sobem para a nuvem Microsoft de qualquer forma. OneDrive também pode causar locks em `.git` (observado: `unable to unlink .git/index.lock`).
5. **`host.docker.internal` sem `extra_hosts`** — a URL do MCP Vision só resolve em Docker Desktop; em Linux puro quebra silenciosamente.

**Médios**
6. Política de senha permissiva (item acima) num serviço exposto via Cloudflare.
7. `X-Karvalho-User` é confiança pura no proxy — o app não valida nada; qualquer exposição direta do container rfnext permite personificação trivial.
8. Sem limite agregado de armazenamento no RF Next (5 MB/request, sem quota por usuário nem total) — esgotamento de disco possível.
9. Container rfnext roda como root, sem HEALTHCHECK.
10. Sem HSTS no gateway (aceitável local; depende 100% do Cloudflare em produção).

**Nota de verificação**: um achado preliminar de "todas as imagens quebradas" foi **descartado** na revisão — era artefato da cópia de auditoria (os PNGs não foram copiados); `web/assets/` existe no disco real com todos os arquivos referenciados. Também não foi possível verificar daqui a pasta externa `..\ROOC AM\conteudo` nem `../RF NEXt` (fora da pasta conectada).

## 6) Plano sugerido para assumir o projeto

**Fase 0 — Estancar risco (fazer já)**
1. `git add -A && git commit` inicial + criar remote privado (GitHub/GitLab) e push. Conferir antes que `.env`, `infra/authentik.env` e `users.caddy` estão de fato fora do stage.
2. Decidir: mover o projeto para fora do OneDrive (recomendado para Docker + git) ou, no mínimo, excluir segredos da sincronização.

**Fase 1 — Resolver as ambiguidades (decisões suas)**
3. RF Next: definir a fonte da verdade — trazer `../RF NEXt` para dentro do repo (ou apontar o build para `projects/rf-next/` se for a mesma coisa) e apagar a cópia perdedora.
4. `users.caddy`/`manage-user.ps1`: remover o mecanismo morto (recomendado, Authentik já cobre) ou religá-lo conscientemente com `basic_auth` em alguma rota.
5. Confirmar se a integração MCP Vision é real na versão externa; se não for, limpar `MCP_VISION_*` do compose e do doc.

**Fase 2 — Higiene**
6. Adicionar `RFNEXT_VISION_TOKEN=` ao `.env.example`; adicionar `extra_hosts: ["host.docker.internal:host-gateway"]` ao rfnext.
7. Incluir backup de `rfnext-data` no checklist; healthchecks básicos para gateway/rfnext/authentik-server.
8. Endurecer política de senha (habilitar zxcvbn e/ou HIBP) e adicionar CSP à rota `auth.*`.
9. Parametrizar admin/slug no `new-authentik-invitation.ps1`.
10. Unificar tokens de cor (importar `brand/tokens/karvalho-colors.css` em vez de duplicar hex).

**Fase 3 — Atualizar o DOCUMENTO_TECNICO.md**
11. Corrigir D1–D7, adicionar `web/assets/`, `brand/`, `projects/`, o fluxo de recovery, o mapeamento `RFNEXT_VISION_TOKEN`→`MCP_VISION_TOKEN` e os riscos da seção 5 acima.

---
*Auditoria executada por agentes paralelos (infra: Opus; frontend e scripts: Sonnet) com planejamento e revisão final Fable, conforme o fluxo padrão do projeto.*
