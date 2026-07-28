# Changelog

## 1.0.4 — 2026-07-28

- o usuário escolhe o executável do jogo uma vez e a escolha fica salva;
- as portas TCP locais são descobertas automaticamente por processo, inclusive
  em reconexões, sem capturar toda a rede;
- suporte a até dois processos do jogo conectados ao mesmo tempo;
- capturas sem pacotes terminam normalmente e não geram exportações vazias;
- logs registram códigos sanitizados para falhas de captura e descoberta.

## 1.0.3 — 2026-07-28

- progresso visível durante consulta, download e verificação da atualização;
- o aplicativo salva o estado e encerra antes de o instalador substituir os arquivos;
- o instalador aguarda o fechamento de versões anteriores sem forçar o processo;
- atualização bloqueada durante captura ativa para evitar perda de dados;
- download parcial nunca é tratado como instalador verificado.

## 1.0.2 — 2026-07-28

- licença e logs persistidos na pasta comum do computador, com migração do formato anterior;
- recuperação de captura PktMon que permaneceu ativa após fechamento ou falha;
- arquivos ETL pendentes podem ser parados e analisados sem serem apagados;
- falha ao iniciar não substitui mais a referência da captura anterior;
- exportação permanece disponível mesmo se a licença não for reconhecida;
- botões de enviar, abrir a pasta e salvar uma cópia sanitizada do log no topo da aba Licença.

## 1.0.1 — 2026-07-28

- log técnico local com rotação automática e limite aproximado de 4 MB;
- remoção defensiva de licença, token, e-mail, IP, UUID e usuário do Windows;
- botão independente **Enviar log técnico** na aba Licença;
- upload somente após confirmação, pelo canal de diagnóstico já autenticado.

## 1.0.0 — 2026-07-28

- ativação e preferências preservadas durante atualizações;
- sessões isoladas a cada encerramento de captura;
- suporte a até dois personagens simultâneos por UID confirmado;
- Profile e nomes de personagens persistidos;
- JSON e CSV separados por personagem e sessão;
- nomes `Profile-Personagem-datahora-contador`;
- EXP bruta e percentual no level;
- aba Informações com tempo, level, EXP, créditos confirmados, contribuição,
  mercado, loot e kills estimadas por recompensa;
- diagnóstico separado sem payload, IP, flow, UID, personagem, chave ou licença;
- atualização estável/beta via release GitHub verificada por Ed25519 e SHA-256.
