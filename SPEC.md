# SPEC — RF NEXT INFO

## Escopo aprovado

- Windows 10/11 x64; grupo fechado; até 25 computadores no primeiro ano.
- Pktmon nativo; sessão manual e contínua; bandeja com escolha na primeira execução.
- Informações atualizadas durante a captura em intervalo configurável, com
  padrão de 30 segundos; EXP e Loot permanecem uma sessão lógica contínua.
- Entrada do personagem, Mercado, Codex e Memory Chips usam janelas marcadas
  de 10 segundos com atalhos próprios, sem iniciar outro Pktmon.
- Atalhos configuráveis; pasta padrão `Documentos\Capturas`.
- Personagem, level, EXP, Mercado, Codex, farm e kills estimadas por recompensa.
- Um Profile com até dois personagens simultâneos, separados por UID confirmado.
- PID, porta e ordem do processo nunca são identidade definitiva de personagem;
  sem UID confirmado, o cliente recebe apenas um nome manual temporário.
- Cada parada cria uma sessão; JSON/CSV são separados por personagem e sessão.
- EXP/Loot permite subsessões manuais ou automáticas por personagem, com
  localização, mobs em multiseleção, nível por mob e opção Outro.
- JSON completo + CSV resumido; SQLite transacional para recuperação.
- Arquivos brutos segmentados sem descarte automático.
- Alertas: 5 GB; 10 GB ou 10% livre; encerramento seguro abaixo de 2 GB livres.
- Após exportar: mostrar tamanhos, validar o arquivo e oferecer envio dos brutos à Lixeira.
- Licença online a cada 24h, tolerância de 72h; depois bloquear novas capturas e preservar exportação.
- A exportação e a recuperação dos arquivos existentes permanecem disponíveis sem licença reconhecida.
- Captura PktMon pendente após falha deve ser recuperável sem apagar o ETL.
- Atualização GitHub stable/beta, visível e confirmada, com manifesto assinado, SHA-256 e rollback de uma versão.
- Sem telemetria; diagnósticos e logs sanitizados só são enviados após consentimento.
- Log técnico local rotativo de até aproximadamente 4 MB; envio, pasta e cópia manual na aba Licença.
- Envio ao site usa API HTTPS idempotente e token revogável por Profile; o
  programa nunca recebe credenciais do banco. O servidor armazena somente o
  hash do token, e o Windows protege a cópia local.
- Interface profissional baseada no kit RF Next da identidade Karvalho. A logo
  oficial é copiada dos assets da marca; mockups gerados não são fonte de logo.

## Marca

Fonte oficial: `K:\Karvalho\Identidade Visual Karvalho`.
Nome do produto: `RF NEXT INFO`.

## Gates

- Pktmon precisa ser comparado com captura real conhecida.
- Antes da atualização periódica, testar se um segmento multi-file fechado é
  legível durante a captura e medir a lacuna real de qualquer stop/start.
- Uma captura segmentada deve preservar frames TCP partidos entre segmentos e
  produzir os mesmos eventos da captura contínua de controle.
- Piloto sem assinatura não é release pública.
- Publicação no GitHub somente após testes e revisão.
