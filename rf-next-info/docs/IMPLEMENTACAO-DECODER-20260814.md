# Implementação do decoder — 14/08/2026

## Origem

- Fonte comparada: `K:\MCP\Karvalho\rf-next\analysis\1.28.5\rfnext_frame_decode.py`.
- SHA-256 da fonte: `D097AD1FA3F21D42A75207B0332CA377E0ED80222627DD814F71405CB4595061`.
- A fonte estava no worktree canônico em desenvolvimento e seu self-test
  retornou `ok`. Por esse motivo, a integração foi feita por contrato e não por
  substituição integral do arquivo do RF QOL.

## Contratos incorporados

| Porta | Opcode | Evento |
|---|---:|---|
| 12010 | `0x0204` | resultado de saída de sala |
| 12010 | `0x0301` | pedido de movimento |
| 12010 | `0x0302` | atualização de movimento |
| 12010 | `0x030A` | lista de entidades que saíram do alcance |
| 12010 | `0x0408` | pedido de teleporte |
| 12010 | `0x0409` | resultado do pedido de teleporte |
| 12010 | `0x040A` | warp de jogador |
| 12010 | `0x040B` | fim do warp |
| 12020 | `0x0501` | pedido de troca de slot equipado |
| 12020 | `0x0502` | resultado da troca de slot equipado |

As aparições de jogador agora também registram explicitamente a entrada no
alcance. A hostilidade continua sendo calculada localmente pela relação entre
guildas; o pacote de aparição não é tratado como fonte direta de hostilidade.

## Integração com o monitor

O evento `disappear_unit_list` remove imediatamente cada `entity_uid` das
âncoras vivas de jogador, monstro e boss no fluxo correspondente. Isso evita
que um personagem visto em outro mapa permaneça no Monitor PvP até o timeout.
O vencimento de quinze segundos continua como proteção para perdas de pacote.

## Compatibilidade preservada

A integração não importou quatro regressões encontradas na fonte em
desenvolvimento:

- continuam decodificados `0x0601` (uso de habilidade) e `0x0609` (seleção de
  alvo), necessários ao alvo atual;
- continuam aceitos os tails de equipamento de 988 e 996 bytes;
- permanece a validação de cabeçalho mínimo nas relações de guilda;
- permanece o caminho adicional dos artefatos Job 1 usado pelo pacote do RF
  QOL.

## Validação

- compilação Python dos módulos alterados: aprovada;
- self-test da fonte canônica: aprovado;
- self-test do decoder incorporado: aprovado;
- 86 testes do núcleo: aprovados;
- suíte completa: 261 testes aprovados em 443,195 segundos;
- `git diff --check`: aprovado.

A mensagem `live_capture_start_failed` emitida durante a suíte é esperada pelo
teste negativo que simula ausência de `Pktmonapi.dll`; ela não representa falha
do resultado.

## Fora do escopo

Esta etapa não altera licença, servidor ou interface. A leitura permanece
passiva por pacotes e não migra o cliente para leitura de memória do processo
do jogo. A implementação foi selecionada para o instalador manual 1.0.8.

## Empacotamento 1.0.8

- versão `1.0.8`, sequência interna `9`;
- commit-fonte limpo: `94ce7cae9bc9a3e2ad08077ccb0b2130414d2822`;
- suíte de release: 261 testes aprovados em 431,527 segundos;
- instalação, autoteste pós-instalação e desinstalação: aprovados;
- instalador: `RF QOL Setup 1.0.8.exe`, 48.369.441 bytes;
- SHA-256: `FF57CD239EA1ED8A0E49F8EEC863874499443B86F4B2461B9F876B7CC297BF1F`;
- ProductVersion e FileVersion: `1.0.8`;
- instalador e executável: `NotSigned`, conforme decisão do owner;
- atualização: manual; nenhum manifesto automático ou assinatura de
  procedência foi gerado;
- Termos de Uso: aceite obrigatório preservado.
- publicação: branch órfã `download/rf-qol-1.0.8`, commit `6d1595b`, sem
  GitHub Release;
- link validado por novo download, com tamanho e SHA-256 idênticos ao candidato:
  `https://github.com/Carvalho3009/RFNextInfo/raw/refs/heads/download/rf-qol-1.0.8/RF%20QOL%20Setup%201.0.8.exe`.
