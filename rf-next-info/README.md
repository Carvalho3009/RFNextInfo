# RF QOL

Cliente Windows 10/11 x64 para captura passiva do RF NEXT 1.28.5, leitura local
e exportação JSON/CSV para o site RF NEXT.

Suporte: [Discord oficial](https://discord.gg/D3hhdMgkj) · `carvalho@tuta.com`

## Recursos atuais

- executável autônomo com identidade visual Karvalho e instalador padrão;
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
- chave enviada somente na ativação; depois, lease Ed25519 v2 renovada
  periodicamente, com tolerância offline máxima de 24 horas;
- estado da licença protegido pelo DPAPI do Windows e recuperável por backup
  criptografado após reinício ou atualização;
- captura, leitura, monitores, exportação e envio bloqueados sem lease válida;
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

O Windows solicita elevação porque o Pktmon precisa de permissão
administrativa. O instalador permite escolher a pasta e coloca nela o
executável, dependências, configurações, banco, logs, cache e a
pasta inicial de capturas. A pasta de capturas e exportações pode ser alterada
dentro do aplicativo. Não existe fallback silencioso para `%AppData%`.
O estado de licença, anti-downgrade e staging de atualização ficam separados em
`%ProgramData%\Karvalho\RF QOL`, com acesso administrativo.

Na primeira abertura:

1. escolha se fechar deve manter a captura visível na área de notificação;
2. ative a instalação na primeira linha de **Configurações**; a ativação será preservada;
3. abra até dois clientes `ProjectRF`; a associação ocorre por UID confirmado;
4. informe o Profile, escolha a pasta de dados e inicie a captura;
5. use os monitores PvE, PvP e Boss junto da captura ou de forma independente;
6. pare a captura, aguarde a leitura e exporte JSON + CSV.

O instalador testa o executável instalado e registra o resultado em
`<pasta escolhida>\logs\install.log`. Ao concluir, abra o programa pelo
atalho.

## Testes e build

```powershell
python -m unittest discover -s tests -v
.\packaging\bootstrap-build.ps1 -Wheelhouse .\tmp\wheels
.\packaging\build.ps1
.\dist\RF QOL\RF QOL.exe --self-test
```

O build de desenvolvimento permanece sem assinatura. O build `-Release` exige
chaves públicas de produção, certificado Authenticode, timestamp, manifesto v2
assinado e NSIS 3.12; enquanto esses recursos não estiverem disponíveis, a
publicação é bloqueada.

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
