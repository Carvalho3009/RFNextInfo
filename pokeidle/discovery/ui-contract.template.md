# Contrato DOM autenticado — roteiro de preenchimento

Não copie classes geradas ou seletores presumidos. Para cada campo de `instances[].selectors`, registre:

- versão/fingerprint visível do cliente;
- tela e pré-condição;
- locator Playwright candidato;
- cardinalidade observada (deve ser exatamente 1);
- texto/atributo que representa o estado;
- pós-condição da ação;
- data da confirmação.

Para cada ação, preencha também `instances[].expectedAccessibleNames` com o nome acessível computado e exato do botão. O runtime exige que o locator estável e `getByRole("button", { name, exact: true })` resolvam para o mesmo elemento; nome vazio, seletor posicional ou divergência causa `SAFE_STOP`.

Estados mínimos: cliente pronto, login necessário, personagem, derrotado, HP, hunt ativa, start/retomar, falta de suprimentos, Auto-Potion e Auto-Revive (toggle e enabled).

Rejeite qualquer locator relacionado a sono/offline, chat, PvP, diamantes, VIP, boost, premium ou loja. Não capture HTML integral, cookies, storage, cabeçalhos, request bodies ou frames WebSocket. Use uma conta de teste autorizada e snapshots DOM sanitizados.
