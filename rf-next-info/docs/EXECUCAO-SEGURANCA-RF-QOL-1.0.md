# Diário de execução — segurança RF QOL 1.0

Branch: `feat/rf-qol-security-1.0`
Worktree: `K:\MCP\_worktrees\rf-qol-security-implementation`
Base: `c85d3b2fd41ed40ff10e8c0ca43f52fe9424b7bd`
Início: 09 ago 2026
Estado: em execução local isolada; sem publicação ou alteração de produção

## Limites autorizados

- Implementação, chaves efêmeras de teste, staging e testes locais: autorizados.
- Uso ou compra de certificado real, chaves privadas reais, produção e release
  pública: não executados nesta branch.
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
| 09 ago 2026 | F1 | Emissor de licença não está presente no monorepo; o site apenas introspecta o serviço externo. | Confirmado |
| 09 ago 2026 | F1 | Contrato v2, cerimônia de chaves, runbook e vetor público determinístico criados. Privada do vetor descartada. | Concluído local |
| 09 ago 2026 | F2 | Cliente agora aceita somente lease v2 Ed25519 por chave pinada de papel `lease-*`, produto/audience/UUID corretos e janela máxima de 24 h. | Concluído local |
| 09 ago 2026 | F2 | Prefixo da licença nova alterado para `RFQ`; `KRV-*`, lease v1 e estado com chave pública mutável são rejeitados. | Concluído local |
| 09 ago 2026 | F2 | Estados `UNACTIVATED`, `ACTIVE_ONLINE`, `ACTIVE_OFFLINE`, `REVALIDATION_REQUIRED`, `EXPIRED`, `REVOKED` e `INVALID_STATE` implementados. | Concluído local |
| 09 ago 2026 | F2 | Gate aplicado a captura, continuidade, monitor, leitura, importação, consulta, exportação e envio nas interfaces Qt e legada. Perda de autorização encerra captura sem ler os brutos. | Concluído local |
| 09 ago 2026 | F2 | Estado de confiança separado em `%ProgramData%\Karvalho\RF QOL`, protegido por DPAPI machine e ACL Administradores/SYSTEM; preferência/banco/log/captura permanecem separados. | Concluído local |
| 09 ago 2026 | F3 | `rf-next/app/server.py` passou a exigir introspecção ativa v2, `rf-qol`, `rf-qol-windows` e instalação idêntica. | Concluído no site local |
| 09 ago 2026 | F3 | Emissão/ativação real não implementada porque o código do emissor é externo e não foi localizado. | Bloqueio externo |
| 09 ago 2026 | F4 | Manifesto v2 fechado, chave distinta `update-*`, SHA-256, tamanho, expiração, sequência e download parcial implementados. | Concluído local |
| 09 ago 2026 | F4 | Authenticode nativo corrigido para ambiente PowerShell 7/Windows PowerShell e reverificado imediatamente antes de abrir o instalador. | Concluído local |
| 09 ago 2026 | F4 | Rollback por cópia de EXE removido. Rollback assinado continua desativado até haver RC anterior e compatibilidade de schema. | Parcial seguro |
| 09 ago 2026 | F5 | Dependências CPython 3.13 fechadas por versão/hash e instaladas offline na própria worktree; SBOM e procedência gerados. | Concluído local |
| 09 ago 2026 | F5 | Build portátil `RF QOL.exe` gerado e autoteste aprovado. Inno Setup não está instalado, portanto nenhum instalador foi produzido. | Parcial |
| 09 ago 2026 | Marca | Logos anteriores removidos; identidade própria RF QOL adicionada em versões principal e símbolo, sem urso/K/Karvalho. | Concluído local |
| 09 ago 2026 | Marca | Nome/título/executável/atalhos renomeados; link exato do Discord adicionado com navegador padrão. | Concluído local |

## Evidências e comandos de validação

- Regressão rápida CPython 3.11: 186 testes aprovados, 23 ignorados por Qt não
  instalado nesse interpretador.
- Regressão final CPython 3.13 no ambiente virtual fechado: 188 testes
  aprovados, nenhum ignorado, em 74,571 s. Inclui vetor público, assinador
  offline, link exato do Discord e smoke offscreen.
- Self-test do site com catálogos canônicos externos apontados por variáveis:
  `OCR parser OK`, exit code 0.
- Auditoria de papéis confirmou chaves lease/update disjuntas; ambos os gates
  `-pending` permaneceram fechados.
- Varredura de código não encontrou `verify=False`, chave privada PEM ou a
  função de rollback inseguro removida.
- Authenticode nativo validado contra `notepad.exe` assinado pela Microsoft;
  publicador divergente é rejeitado pelos testes.
- Gates de release de lease/update falharam como esperado enquanto as públicas
  têm `-production-pending`.
- O build de desenvolvimento é deliberadamente `NotSigned`; não é release nem
  deve ser distribuído.
- O build recusará release sem Inno Setup, certificado/timestamp, chave privada
  offline de update e substituição das públicas placeholder.
- Fable: nenhuma nova chamada foi necessária nesta execução; a revisão anterior
  continua complementar e, conforme autorizado, não bloqueia o avanço local.

## Identidade visual

- Assets finais: `assets/rf-qol-primary-v1.png` e
  `assets/rf-qol-symbol-v1.png`.
- Geração: ImageGen embutido, usando a identidade Karvalho somente como
  referência de nível de acabamento, paleta e proporção.
- Direção: monograma geométrico original R/Q, ouro facetado, texto exato
  `RF QOL`, fundo transparente, sem urso, K, Karvalho ou RF NEXT QOL.
- Os quatro PNGs antigos foram removidos desta branch. A remoção é recuperável
  pelo Git e não afetou a beta em uso.

## Pendências externas reais

1. código/acesso ao emissor para implementar e provar ativação/renovação/
   revogação v2 em staging;
2. cerimônia das chaves de produção;
3. certificado Authenticode Karvalho e timestamp RFC 3161;
4. Inno Setup para produzir o instalador;
5. RC anterior assinada para implementar/testar rollback seguro;
6. Windows 10/11 limpos, licença real e teste com até dois clientes;
7. G4 do owner para qualquer publicação ou produção.

## Rollback

Enquanto não houver integração externa, o rollback é descartar a branch/worktree
de implementação. A Beta publicada e os dados reais permanecem intactos.
