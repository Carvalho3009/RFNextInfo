# RF NEXT INFO

Cliente Windows 10/11 x64 para captura passiva do RF NEXT 1.28.5, leitura local
e exportação JSON/CSV para o site RF NEXT.

Contato: Discord `Carvalho` · `carvalho@tuta.com`

## Piloto entregue

- executável autônomo, interface Karvalho e instalador padrão;
- captura nativa Pktmon em TCP/12000 e TCP/12020, segmentada em 512 MB;
- SQLite WAL para recuperação e reprocessamento incremental;
- Codex/coleção, personagem, level, EXP, mercado e eventos de farm quando o
  decoder canônico possui semântica confirmada;
- kill exibida apenas como estimativa por evento de recompensa;
- chave enviada somente na ativação; depois, lease Ed25519 renovada a cada
  24 horas, com tolerância offline de até 72 horas;
- exportação com lease e `installation_id`, nunca com a chave da licença;
- atualização GitHub sempre visível, com changelog, confirmação, assinatura
  Ed25519 e SHA-256; sem atualização silenciosa;
- sem injeção, driver próprio, UPX, ofuscação agressiva, telemetria ou
  mecanismo para contornar antivírus.

## Armazenamento

Os segmentos brutos podem crescer rapidamente:

- amarelo a partir de 5 GB;
- vermelho a partir de 10 GB ou menos de 10% do disco livre;
- parada segura abaixo de 2 GB livres.

Depois de exportar, o aplicativo informa os tamanhos e oferece mover os
segmentos para a Lixeira. Nenhuma exclusão permanente é automática.

## Executar

Use [RFNextInfo-Setup-0.1.1-pilot.exe](dist/RFNextInfo-Setup-0.1.1-pilot.exe)
ou o portátil [RFNextInfo.exe](dist/RFNextInfo.exe). O Windows solicita
elevação porque o Pktmon precisa de permissão administrativa.

Na primeira abertura:

1. escolha se fechar deve manter a captura visível na área de notificação;
2. ative a instalação na aba **Licença**;
3. informe o personagem, inicie a captura e jogue normalmente;
4. pare a captura, aguarde a leitura e exporte JSON + CSV.

## Testes e build

```powershell
python -m unittest discover -s tests -v
python -m PyInstaller --clean --noconfirm .\packaging\RFNextInfo.spec
makensis.exe .\packaging\installer.nsi
.\dist\RFNextInfo.exe --self-test
```

O piloto ainda exige a validação visual e funcional operada pelo proprietário
em uma máquina limpa com Windows Defender e Kaspersky. A versão pública final
permanece bloqueada até assinatura de código confiável.
