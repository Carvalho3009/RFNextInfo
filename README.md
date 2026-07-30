# RF NEXT INFO

Cliente Windows 10/11 x64 para captura passiva do RF NEXT 1.28.5, leitura local
e exportação JSON/CSV para o site RF NEXT.

Contato: Discord `Carvalho` · `carvalho@tuta.com`

## Versão 1.0

- executável autônomo, interface Karvalho e instalador padrão;
- seleção única do executável e detecção automática das conexões TCP atuais;
- lista limitada aos executáveis `ProjectRF*`;
- captura nativa Pktmon limitada às portas conhecidas do RF NEXT e às portas
  locais descobertas, segmentada em 512 MB;
- SQLite WAL para recuperação e reprocessamento incremental;
- Codex/coleção, personagem, level, EXP, mercado e eventos de farm quando o
  decoder canônico possui semântica confirmada;
- kill exibida apenas como estimativa por evento de recompensa;
- sessões independentes, Profile e até dois personagens capturados
  automaticamente, sem seleção manual de processo;
- JSON e CSV separados por personagem, com EXP bruta e percentual no level;
- sem UID, a exportação pede a EXP atual (%) dos personagens e associa cada
  conexão ao valor observado mais próximo;
- identificação incompleta não bloqueia a exportação: o arquivo recebe
  `requires_site_review` para validação na importação do site;
- aba Informações por personagem e diagnóstico sanitizado separado para
  eventos ainda não decodificados;
- log técnico local rotativo de até aproximadamente 4 MB, com remoção de
  dados sensíveis, envio manual e salvamento de cópia pela aba Licença;
- recuperação de captura PktMon pendente após fechamento inesperado, sem
  apagar os segmentos ETL;
- curva de EXP 1–200 e catálogo local de 1.322 itens de loot conhecidos;
- chave enviada somente na ativação; depois, lease Ed25519 renovada a cada
  24 horas, com tolerância offline de até 72 horas;
- estado da licença protegido pelo DPAPI do Windows e recuperável por backup
  criptografado após reinício ou atualização;
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

Use [RFNextInfo-Setup-1.0.8.exe](dist/RFNextInfo-Setup-1.0.8.exe). O Windows
solicita elevação porque o Pktmon precisa de permissão administrativa. As
dependências ficam instaladas junto ao programa, sem extração temporária
`_MEI`.

Na primeira abertura:

1. escolha se fechar deve manter a captura visível na área de notificação;
2. ative a instalação na aba **Licença**; a ativação será preservada;
3. abra o jogo, atualize a lista e escolha o executável uma vez;
4. informe o Profile e os personagens, inicie a captura e jogue normalmente;
5. pare a captura, aguarde a leitura e exporte JSON + CSV.

O instalador testa o executável instalado e registra o resultado em
`C:\ProgramData\Karvalho\RFNextInfo\logs\install.log`. Ao concluir, abra o
programa pelo atalho.

## Testes e build

```powershell
python -m unittest discover -s tests -v
python -m PyInstaller --clean --noconfirm .\packaging\RFNextInfo.spec
makensis.exe .\packaging\installer.nsi
.\dist\RFNextInfo\RFNextInfo.exe --self-test
```

O instalador ainda não possui assinatura Authenticode. A autenticidade das
atualizações é validada internamente por Ed25519 e SHA-256.

### Diagnóstico da atualização durante a captura

Antes de habilitar a rotação temporizada, execute em PowerShell como
Administrador:

```powershell
.\tools\Test-PktmonLive.ps1
```

O teste aborta se já houver captura ou filtros PktMon ativos, preserva os ETLs
gerados e grava `resultado.json` em
`Documentos\Capturas\Diagnosticos\pktmon-live-*`. Ele mede a conversão de um
segmento fechado enquanto a captura continua e o intervalo real de
`stop`/`start`.

Para validar o streaming contínuo sem parar a captura:

```powershell
python .\tools\Test-PktmonRealtime.py --seconds 30
```
