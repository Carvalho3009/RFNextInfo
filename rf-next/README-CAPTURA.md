# Captura nativa do RF Next no Windows

Execute `Capturar Trafego RF Next.exe` para abrir a interface sem terminal (o arquivo `.cmd` continua disponível como alternativa). Ela mostra tempo decorrido, progresso da captura, contadores e a lista de timestamps. Use os botões ou os atalhos globais, que continuam funcionando com o jogo em primeiro plano:

Execute `Monitorar Mercado RF Next.exe` uma vez e deixe-o residente na bandeja do Windows. Ele começa aguardando, sem abrir janela: `Ctrl+Alt+A` inicia a captura e `Ctrl+Alt+S` encerra a sessão, salva e importa o histórico, mas não fecha o programa. A captura guarda somente TCP/12020 e verifica a cada 15 segundos se chegou uma lista completa nova. Para fechar definitivamente, use **Sair do programa** no ícone da bandeja. O `.cmd` permanece apenas como alternativa visual de diagnóstico.

Com o cliente PC aberto, clique em **Iniciar captura**, espere a mensagem **Capturando** e só então abra a tela Mercado. A captura acontece no Windows e não usa o BlueStacks.

- `Ctrl+Alt+E`: EXP
- `Ctrl+Alt+M`: mob
- `Ctrl+Alt+L`: loot
- `Ctrl+Alt+A`: leilão
- `Ctrl+Alt+S`: encerrar e salvar

Cada sessão gera um `.pcap` e um `.events.csv` com o mesmo nome. O CSV contém o timestamp calibrado para o relógio do PCAP, horário local, tempo desde o início, evento e incerteza da sincronização.

Para atualizar o Mercado, inicie a captura antes de abrir essa tela no cliente PC, abra o Mercado e encerre a captura. Quando a resposta completa for encontrada, o programa cria automaticamente `captures\market.csv`, já no formato aceito pelo site, e a registra nas tabelas históricas do SQLite quando o container `karvalho/rfnext` estiver ativo. O arquivo contém uma linha por item+refino, com menor preço, maior preço e quantidade total registrada. O arquivo anterior e o banco só são atualizados depois que uma lista completa é validada.

O programa captura o tráfego TCP/UDP da interface de Internet padrão do Windows e decodifica passivamente apenas as mensagens conhecidas do Mercado.

Feche outros programas que usam a Internet durante a coleta. Como o Npcap não filtra por processo, o PCAP inclui o tráfego deles e pode conter metadados de conexão.

Uso opcional no PowerShell:

```powershell
.\Capturar-Trafego.ps1 -DurationSeconds 60
.\Capturar-Trafego.ps1 -CaptureInterface 'Ethernet 2'
.\Capturar-Trafego.ps1 -SelfTest
```

Use `-SkipMarketCsv` quando quiser guardar somente o PCAP ou `-SkipMarketDatabase` para gerar o CSV sem registrar uma fotografia no site. Requisitos presentes neste ambiente: Wireshark/Npcap, Python 3 e Docker para a publicação. BlueStacks, root, ADB e Ghidra não são usados.
