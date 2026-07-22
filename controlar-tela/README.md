# Ronaldinho — Proteção por Barra de Vida

**Versão 1.3.0 — Dibre a concorrência**

A visão geral exibe lado a lado os status das duas janelas. Use os menus laterais para abrir a configuração da janela selecionada.

Nesta versão, os teleportes **Safe** e **Random** possuem marcações próprias e o tipo usado pode ser escolhido por janela.

Programa portátil para Windows que monitora até duas janelas de forma independente. Ele reconhece a parte vermelha da barra de vida e pode executar uma sequência de teleporte e spots quando a vida cair além do limite configurado.

## Requisitos

- Windows 10 versão 2004 ou mais recente, ou Windows 11, 64 bits.
- Executar como administrador para que os cliques funcionem em programas também executados como administrador.
- A janela monitorada pode ficar coberta por outras janelas, mas não pode ficar minimizada.
- Esta distribuição já inclui o .NET necessário; não há instalador.

## Primeira execução

1. Extraia todo o conteúdo do ZIP para uma pasta comum.
2. Abra `ControlarTela.exe`.
3. Confirme a solicitação de administrador do Windows.
4. Se o SmartScreen avisar que o arquivo não é reconhecido, confira se o arquivo veio de uma fonte confiável. O programa não possui assinatura digital.
5. Abra a janela do jogo ou programa que será monitorado.
6. No ControlarTela, clique em **Atualizar janelas**.

As configurações são salvas somente para o usuário atual em:

`%LOCALAPPDATA%\ControlarTela\config.json`

## Atualizações automáticas

Ao abrir, o programa consulta a versão mais recente publicada em
[`Carvalho3009/ronaldinho-protecao`](https://github.com/Carvalho3009/ronaldinho-protecao/releases).
Quando houver uma versão nova, escolha **Sim** para baixar, substituir o executável e reiniciar automaticamente.
Também é possível usar **Verificar atualização** no topo da tela.

## Configurando cada janela

Repita estes passos nas abas **Janela 1** e **Janela 2** que desejar usar.

### 1. Escolha a janela

1. Clique em **Janela** no menu lateral e selecione a janela correta na lista.
2. Ative **Proteção ativa** para monitorá-la.
3. Use **Segundo plano** para não mover o mouse nem entregar o foco ao jogo.

A proteção pode ser ativada ou desativada individualmente durante a sessão. Desativar uma janela preserva o tempo e a posição atual da sequência; a outra continua funcionando.

### 2. Marque a barra de vida cheia

Este passo precisa ser feito com a vida realmente em 100%.

1. Recupere completamente a vida.
2. Clique em **Barra de vida** no menu lateral e use **Marcar barra**.
3. Arraste o retângulo exatamente sobre a barra, incluindo toda a extensão que o vermelho ocupa quando cheia.
4. Confirme a marcação.
5. Confira se o visualizador mostra **Vida: 100%**.

O programa mede somente a largura vermelha. Números brancos, fundo, moldura e faixas de outras cores são ignorados. Se a leitura estiver incorreta, remarque a barra com a vida cheia.

### 3. Configure o teleporte

1. Clique em **Teleporte** no menu lateral.
2. Use **Marcar Safe** e/ou **Marcar Random** para registrar cada posição.
3. Em **Usar teleporte**, escolha qual deles será clicado quando a vida cair.

### 4. Defina o limite

Em **Reagir ao cair**, informe a queda permitida.

Exemplo: limite de `40%` executa a reação quando a vida chegar aproximadamente a `60%` ou menos.

## Usando somente o teleporte

Desative **Usar spots** no cartão **Rota de spots**. Quando o limite for atingido, o programa clicará somente no item de teleporte.

## Configurando spots

Se quiser escolher um spot após usar o item de teleporte:

1. Ative **Usar spots** no cartão **Rota de spots**.
2. Abra manualmente a janela de spots no jogo.
3. Clique em **Rota de spots** na barra lateral.
4. Use **Janela de spots** para selecionar a área que identifica o menu.
5. Use **Abrir menu** para marcar o botão que abre os spots.
6. Use **Botão Teleportar** para marcar o botão de confirmação.
7. Use **Adicionar** para cadastrar cada posição.
8. Ative na lista somente os spots que participarão da sequência e defina quantas vezes a rota será repetida.

Para substituir toda a rota de uma vez, use **Reiniciar spots**. Após a confirmação, clique no primeiro spot; o programa abrirá imediatamente a marcação seguinte. Continue clicando nos spots na ordem desejada e pressione `Esc` para concluir. Se `Esc` for pressionado antes do primeiro ponto, a rota anterior será mantida.

Os spots podem ser ativados ou desativados durante a sessão. A sequência ignora os spots desmarcados.

Em **Configurações**, ajuste **Tentativas no botão Teleportar**. Após cada clique, o programa verifica se a janela de spots fechou. Se ela continuar aberta por stagger ou lag, o botão é acionado novamente usando o **Intervalo entre cliques**. Se todas as tentativas falharem, a proteção daquela janela pausa sem avançar o spot ou o ciclo.

## Tempo da sessão

No menu lateral **Sessão**, defina as horas e os minutos de cada janela. O contador considera apenas o tempo em que aquela proteção está ativa. Ao terminar, a janela é desativada automaticamente. A visão geral mostra o tempo ativo e o restante no cartão **Sessão**.

## Iniciando

1. Deixe as janelas monitoradas abertas e não minimizadas.
2. Clique em **Iniciar proteção**.
3. Acompanhe na **Visão geral** o estado, o tempo, a vida estimada e a próxima reação das duas janelas.
4. Use **Parar proteção** para interromper todas as janelas.

Se a barra desaparecer ou a captura parar, somente aquela janela entra em **Procurando barra**. O contador e as ações ficam pausados, e uma nova tentativa ocorre a cada 5 segundos. Quando o vermelho reaparecer, a rotina volta automaticamente do ponto em que parou.

## Solução de problemas

### O clique não funciona

- Feche o programa e abra `ControlarTela.exe` como administrador.
- Confirme que a janela escolhida ainda é a correta.
- Em **Configurações**, use os botões de teste antes de iniciar a proteção.

### A captura não encontra a barra

- Restaure a janela monitorada; ela não pode ficar minimizada.
- Clique em **Atualizar janelas** e selecione novamente a janela correta.
- Remarque somente a barra vermelha com a vida cheia.
- Não use uma marcação que inclua outra área vermelha fora da barra.

### A porcentagem está incorreta

- Recupere a vida até 100% e refaça **Marcar barra de vida**.
- Confira se a seleção cobre toda a largura vermelha cheia.
- Não inicie usando uma configuração copiada de outro computador ou resolução.

### O mouse fica preso no Parsec

O bloqueio é controlado pelo Parsec no computador cliente. Pressione `Ctrl+Alt+Z` no computador original para liberar temporariamente o mouse. `Ctrl+Shift+W` alterna o Parsec para o modo janela.

## Observações

- As posições dependem da resolução, escala e layout de cada janela. Configure novamente ao trocar de computador ou resolução.
- O ZIP não inclui as configurações e posições do computador de quem o criou.
- Verifique as regras e os termos do programa ou jogo monitorado antes de usar automação.
