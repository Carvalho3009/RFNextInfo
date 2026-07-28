# Changelog

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
