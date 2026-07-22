# Documento Técnico Consolidado

**Data:** 22 de julho de 2026  
**Autor:** Compilado por análise local em múltiplos repositórios  

Este documento consolida o estado técnico atual dos projetos abaixo, com foco em arquitetura, execução, implantação, riscos e pontos de manutenção:

- [ROOC AM](#rooc-am)
- [Site](#site)
- [RF Next](#rf-next)
- [Poke Idle](#poke-idle)
- [Controlar tela](#controlar-tela)
- [MCP (infraestrutura)](#mcp)

## 1) Visão consolidada

| Projeto | Caminho principal | Natureza | Papel no ecossistema |
| --- | --- | --- | --- |
| ROOC AM | `K:\MCP\projects\rooc-americas` | Conteúdo editorial + controle de guia | Base de conhecimento/comunicação para ROOC Americas |
| Site | `C:\Users\celc3\OneDrive\Documentos\Site` | Hospedagem e projetos de front/services | Ponte de publicação e integração dos projetos |
| RF Next | `C:\Users\celc3\OneDrive\Documentos\RF NEXt` | Coleta e análise técnica do jogo | Subsistema de observação/telemetria para pesquisa |
| Poke Idle | `K:\MCP\projects\pokeidle` | Projeto web com deployment via Docker | Serviço de aplicação independente |
| Controlar tela | `K:\MCP\projects\controlar-tela` | Aplicação para controle de ambiente visual local | Utilitário de uso local/comercialização |
| MCP | `K:\MCP\stack` | Plataforma de serviços (Docker) | Camada base de integração e automação |

---

## 2) ROOC AM

### 2.1 Escopo
Repositório de referência editorial para guia de Ragnarok Origin Classic na América.

### 2.2 Fontes técnicas
- `K:\MCP\projects\rooc-americas\conteudo\README.md`
- `K:\MCP\projects\rooc-americas\mockup\README.md`
- `C:\Users\celc3\OneDrive\Documentos\ROOC AM\conteudo\GUIA-ROOC-AMERICAS.md`
- `C:\Users\celc3\OneDrive\Documentos\ROOC AM\conteudo\README.md`

### 2.3 Estrutura lógica
- `conteudo/`: base documental e guias finais (estrutura de seções por classe/assunto).
- `mockup/`: materiais de referência de layout/versão.
- Pasta de OneDrive com duplicidade de conteúdo editorial, utilizada para validação manual e backup.

### 2.4 Tecnologias e padrões observados
- Conteúdo orientado a publicação textual e checklist de confiança.
- Padrões de rotulagem de confiança: notas de opinião e validação explícita.
- Workflow de validação de mídia com `youtube` metadata e fallback por cliente Android.

### 2.5 Operação prática
- Atualização de guia via revisão dos arquivos em `conteudo`.
- Validação de fontes externas com conferência por vídeo/metadata.
- Publicação e revisão por revisão de checklist e rótulos de confiança no documento.

### 2.6 Riscos e manutenção
- Fonte cruzada depende de arquivos duplicados (MCP + OneDrive): reduzir risco de divergência com uma fonte mestre.
- Falta de CI para validar integridade do texto e checagem automática de links.
- Linguagem/versão do jogo pode tornar trechos de guia obsoletos; manter revisão periódica por patch.

---

## 3) Site

### 3.1 Escopo
Diretório raiz de coordenação dos projetos com orquestração de serviços de publicação.

### 3.2 Fontes técnicas
- `C:\Users\celc3\OneDrive\Documentos\Site\README.md`
- `C:\Users\celc3\OneDrive\Documentos\Site\compose.yml`
- `C:\Users\celc3\OneDrive\Documentos\Site\projects\rf-next\Dockerfile`

### 3.3 Estrutura lógica
- `compose.yml`: centraliza serviços e dependências do ambiente local.
- Diretório de projetos integrados (`projects/`) com configuração específica por app.
- Configurações auxiliares para acesso e build publicados localmente.

### 3.4 Padrões de execução
- Uso de Docker Compose como padrão para subir serviços.
- Cada projeto embutido mantém seu próprio Dockerfile/stack.
- Recomendação de rebuild do serviço alterado para reduzir tempo de ciclo.

### 3.5 Riscos e manutenção
- Dependência de múltiplos repositórios auxiliares (ex.: `rf-next`) exige versionamento consistente de portas, tags e `.env`.
- Verificações de saúde devem incluir rotas de API e auth (`/api/state` em cenários de integração com projeto interno).
- Sem um manifesto único de versões, mudanças em subprojetos podem gerar comportamentos assíncronos entre stacks.

---

## 4) RF Next

### 4.1 Escopo
Projeto técnico de captura e análise de tráfego passivo e documentação de equilíbrio/funcionalidades.

### 4.2 Fontes técnicas
- `C:\Users\celc3\OneDrive\Documentos\RF NEXt\Dockerfile`
- `C:\Users\celc3\OneDrive\Documentos\RF NEXt\README-CAPTURA.md`
- `C:\Users\celc3\OneDrive\Documents\RF NEXt\Capturar-Trafego.ps1`
- `C:\Users\cel3c\OneDrive\Documentos\RF NEXt\analysis\1.28.5\RFNext-Handoff-Projeto-Offline-1.28.5.md`
- `C:\Users\cel3c\OneDrive\Documentos\RF NEXt\analysis\1.28.5\RFNext-Drop-e-Multiplicador-EXP.md`

### 4.3 Arquitetura técnica
- Coleta passiva via ADB/tcpdump no emulador (ex.: serial `emulator-5574` em cenários observados).
- Parser dedicado para sumarização de PCAP (`pcap_summary.py`) para reduzir carga de análise manual.
- Scripts auxiliares para automação de captura.
- Pastas de handoff por versão para preservar evidências e linha temporal de decisão.

### 4.4 Fluxo de implantação/uso
- Provisionar dispositivo/emulador + ADB.
- Executar captura com script dedicado.
- Converter PCAP com ferramenta de resumo para leitura operacional.
- Registrar evidências e decisões em documento de handoff versionado.

### 4.5 Restrições técnicas e segurança
- Limitação conhecida: tráfego pode não permitir inferência de regras sensíveis sem contexto adicional (ex.: payloads cifrados/alta entropia).
- A captura é útil para diagnóstico e evidência, mas não deve ser tratada como prova de mecânica interna sem confirmação de protocolo decodificado.

### 4.6 Riscos e manutenção
- Dependência de versões do Android Debug Bridge e do emulador.
- Scripts Windows precisam tratar nomes de dispositivo e paths voláteis.
- Necessidade de manutenção contínua por patch do jogo e atualização de clientes.

---

## 5) Poke Idle

### 5.1 Escopo
Aplicação web de jogo/tool com implantação de serviço persistente e operação Docker.

### 5.2 Fontes técnicas
- `K:\MCP\projects\pokeidle\README.md`
- `K:\MCP\projects\pokeidle\package.json`
- `K:\MCP\projects\pokeidle\docker-compose.yml`
- `K:\MCP\projects\pokeidle\.env.example`
- `C:\Users\celc3\OneDrive\Documentos\Poke Idle\README.md`
- `C:\Users\celc3\OneDrive\Documentos\Poke Idle\docker-compose.yml`

### 5.3 Arquitetura
- Serviço principal definido em `docker-compose.yml` com variáveis de ambiente.
- Dependências do projeto descritas em `package.json` para runtime Node.
- Exposição de endpoint persistente (porta local padrão documentada no `.env.example`).

### 5.4 Operação
- Bootstrap via `.env.example` para criar `.env` local.
- `docker-compose up` para subir dependências e aplicação.
- Ajustes funcionais devem começar no projeto em `K:\MCP\projects\pokeidle` (cópia canônica).

### 5.5 Riscos e manutenção
- Divergência entre cópia MCP e cópia OneDrive do mesmo projeto.
- Falta de lockfile/documentação de ambiente em sincronia gera ambiguidade de versões.
- Serviços externos (se houver) precisam checagem explícita no `README`.

---

## 6) Controlar tela

### 6.1 Escopo
Aplicação utilitária de controle de tela/uso local, com build publicado em release.

### 6.2 Fontes técnicas
- `K:\MCP\projects\controlar-tela\README.md`
- `C:\Users\celc3\OneDrive\Documentos\Controlar tela\release-upload-v1.1.0\ControlarTela.exe`

### 6.3 Arquitetura e operação
- Código-fonte e documentação em `K:\MCP\projects\controlar-tela`.
- Artefatos binários em pasta de release para distribuição.
- Readme descreve instalação, uso e requisitos básicos.

### 6.4 Riscos e manutenção
- Sincronizar hash/versão do executável com código-fonte da branch corrente.
- Garantir canais de atualização claros (release vs repositório fonte).
- Para publicação, validar checksum e caminho de instalação em cada release.

---

## 7) MCP (infraestrutura)

### 7.1 Escopo
Camada de integração, automação local e execução de serviços suportes para os projetos.

### 7.2 Fontes técnicas
- `K:\MCP\stack\README.md`
- `K:\MCP\stack\docker-compose.yml`
- `K:\MCP\stack\.env.example`
- `K:\MCP\local-ai-mcp\README.md`
- `K:\MCP\local-ai-mcp\pyproject.toml`
- `K:\MCP\local-ai-mcp\.env.example`
- `K:\MCP\control\README.md`
- `K:\MCP\control\main.py`
- `K:\MCP\control\orchestrator.py`
- `K:\MCP\host-worker\.env.example`

### 7.3 Stack e componentes
- Orquestração por Docker Compose em `K:\MCP\stack`.
- Serviços especializados por pasta:
  - `local-ai-mcp` (serviço principal de automação/integração local).
  - `control` (orquestração e utilitários de controle).
  - `host-worker` (worker para execução de tarefas).
- Ambientes parametrizados via `.env` e `.env.example`.

### 7.4 Fluxo operacional padrão
- Definir/revisar variáveis no `K:\MCP\stack\.env` a partir do exemplo.
- Subir a stack com `docker-compose`.
- Validar que serviços levantam e dependências entre si estão estáveis.
- Conferir logs por serviço para confirmar readiness.

### 7.5 Riscos e manutenção
- Ambientes diferentes entre diretórios podem causar conflito de variáveis.
- Alterações em runtime de `local-ai-mcp` exigem revisão coordenada do `pyproject.toml` e dependências.
- Serviços de controle devem manter isolamento e limites para evitar impacto no host.

---

## 8) Mapa de dependências entre projetos

- `ROOC AM` e `RF Next` concentram documentação e pesquisa; geralmente consomem infraestrutura de publicação do `Site`.
- `RF Next` pode gerar evidências e conteúdos que retroalimentam guias do `ROOC AM`.
- `Poke Idle`, `Controlar tela` e demais apps podem compartilhar a mesma base de deploy/gestão em `K:\MCP\stack`.
- A camada MCP é recomendada como padrão de operação para evitar scripts divergentes por projeto.

---

## 9) Matriz de riscos técnicos

| Projeto | Risco principal | Impacto | Mitigação |
| --- | --- | --- | --- |
| ROOC AM | Conteúdo duplicado em múltiplas pastas | Inconsistência editorial | Definir fonte única de publicação e revisão |
| Site | Dependências ambientais cruzadas | Falhas de build inesperadas | Padronizar `.env` e versionamento por serviço |
| RF Next | Alterações em protocolo/cliente Android | Perda de leitura de tráfego | Atualizar scripts por versão e manter handoff por versão |
| Poke Idle | Divergência canônica/OneDrive | Deploy com comportamento diferente | Usar `K:\MCP\projects\pokeidle` como único operacional |
| Controlar tela | Release sem trilha de controle | Dificuldade de rollback | Adotar changelog por versão de release |
| MCP | Variáveis e dependências heterogêneas | Serviços instáveis | Auditoria trimestral de `compose` e `.env` |

---

## 10) Próximos passos recomendados

1. Normalizar **uma pasta-mãe oficial** por projeto para operação e publicação.
2. Definir checklist técnico único por projeto com:
   - pré-requisitos,
   - comando de inicialização,
   - verificação de integridade (smoke check),
   - rollback.
3. Consolidar documentação operacional em linguagem única e com seções fixas: `Objetivo`, `Arquitetura`, `Deploy`, `Troubleshooting`, `Riscos`.
4. Automatizar validação mínima com script por projeto (checagem de arquivos críticos e variáveis obrigatórias).
5. Registrar matriz de contato e propriedade de cada projeto para evitar acoplamento indevido entre ambientes.

