# SPEC — RF NEXT INFO

## Escopo aprovado

- Windows 10/11 x64; grupo fechado; até 25 computadores no primeiro ano.
- Pktmon nativo; sessão manual e contínua; bandeja com escolha na primeira execução.
- Atalhos configuráveis; pasta padrão `Documentos\Capturas`.
- Personagem, level, EXP, Mercado, Codex, farm e kills estimadas por recompensa.
- Um Profile com até dois personagens simultâneos, separados por UID confirmado.
- Cada parada cria uma sessão; JSON/CSV são separados por personagem e sessão.
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

## Marca

Fonte oficial: `K:\Karvalho\Identidade Visual Karvalho`.
Nome do produto: `RF NEXT INFO`.

## Gates

- Pktmon precisa ser comparado com captura real conhecida.
- Piloto sem assinatura não é release pública.
- Publicação no GitHub somente após testes e revisão.
