# Núcleo de captura

O núcleo é offline e não conhece licença, GitHub ou rede de aplicação.
`metadata.installation_id` e `metadata.license_lease` saem nulos para a camada
do aplicativo preencher; chave de licença nunca pertence ao arquivo.

## Fluxo

1. `connections` descobre as portas TCP locais do executável selecionado;
2. `PktmonCapture` configura somente essas portas e inicia `pktmon` com pacote inteiro,
   arquivo de 512 MiB e modo `multi-file`.
3. O observador encerra com segurança abaixo de 2 GiB livres.
4. ETL é convertido por `pktmon etl2pcap`; PCAPNG padrão é reduzido a PCAP
   temporário para o decoder canônico.
5. Apenas eventos reconhecidos são persistidos em SQLite/WAL. `0x0101` é
   descartado antes de qualquer persistência.
6. JSON e CSV são gravados localmente; o JSON é reaberto e validado antes de
   ser considerado exportado.

## Decoder

Durante desenvolvimento, o adaptador usa
`K:\MCP\Karvalho\rf-next\analysis\1.28.5\rfnext_frame_decode.py`. O build
standalone deve incluir uma cópia byte a byte desse arquivo como
`core\rfnext_frame_decode.py`; também é possível informar
`RFNEXT_DECODER_PATH`. Não existe segunda implementação do protocolo.

## Limites confirmados

- O Pktmon oferece segmentação ETL nativa, mas não fornece ao programa frames
  decodificados em tempo real. A tela pode mostrar tamanho, espaço e estado da
  captura em andamento; dados de jogo surgem após converter/reprocessar um
  segmento ETL fechado.
- PCAPNG aceita os blocos padrão SHB/IDB/EPB e linktype Ethernet (1) ou Linux
  SLL (113). Blocos de metadados do Pktmon são ignorados.
- Kills são **proxy**: contagem dos eventos de recompensa `0x040A`, nunca morte
  confirmada.
- Porta cliente não é identidade durável. Quando `0x0106` aparece, o
  `character_uid` confirmado é persistido no próprio evento; a correlação
  automática desse UID com todos os eventos da sessão ainda depende de
  evidência/protocolo adicional.
- PCAP/PCAPNG fornecidos diretamente funcionam offline. ETL exige Windows com
  `pktmon`.

Referências: documentação Microsoft de
[`pktmon start`](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-start),
[`pktmon filter add`](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-filter-add)
e [`pktmon etl2pcap`](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-etl2pcap).

## Verificação

```powershell
python -m unittest discover -s tests -v
```
