# Banco PvP e overlays — RF QOL 1.0

Data: 11 ago 2026
Estado: implementação local validada; ajustes complementares em
`SPEC-CORRECOES-BANCO-PVP-INVENTARIO-ENVIOS-1.0.md`

## Escopo

- dividir o overlay PvP em três janelas móveis: **Alvo atual**,
  **Próximos hostis** e **Próximos não hostis**;
- criar a aba **Banco PvP** com UID, Personagem, Guilda e Status;
- preencher Guilda e Status observado pelo decoder das relações entre guildas;
- permitir alterar manualmente a Guilda e o Status entre Aliado, Inimigo,
  Neutro e Ignorar;
- sincronizar os campos sanitizados pelo endpoint de observações já existente.

## Regras

- UID é a chave única; novas leituras atualizam o mesmo registro.
- Um UID novo recebe Status **Neutro** até existir relação observada.
- **Inimigo** aparece em Próximos hostis.
- **Aliado** e **Neutro** aparecem em Próximos não hostis, com o status visível.
- O alvo atual depende da seleção/combate confirmado e não do status manual.
- O alvo atual não é repetido nas listas de próximos.
- A retenção visual permanece em três segundos.
- Guilda e status observados são atualizados pelo jogo e pelo site enquanto não
  houver uma escolha manual para o respectivo campo.
- Uma escolha manual tem prioridade sobre observações posteriores.
- Status e guilda manual carregam data própria de alteração. Na sincronização,
  vence o valor com data mais recente para o respectivo campo; a data geral da
  observação não sobrescreve uma decisão manual mais nova.

## Segurança e privacidade

O contrato mantém somente campos decodificados. Não são enviados payload
bruto, endereço de rede, token, senha, ticket ou opcode `0x0101`. A rota do
site continua exigindo token do Profile, lease v2 válida e chave de
idempotência.

## Aceite

- as três janelas usam somente o cliente selecionado no Monitor PvP;
- cada janela pode ser movida e conserva sua própria posição;
- minimizar o programa não oculta overlays ativos;
- mudança de guilda/status persiste após reiniciar;
- registros duplicados do mesmo UID são mesclados;
- o site valida os quatro status e devolve os campos consolidados;
- testes cobrem classificação, edição, conflito temporal, envio e isolamento
  entre clientes.

## Validação local

- programa: 237 testes aprovados e 1 ignorado porque a área de notificação não
  está disponível no ambiente de teste;
- servidor: compilação e autoteste integral aprovados com importação
  idempotente, validação dos quatro status e devolução consolidada;
- revisão Fable não executada porque a sessão OAuth do Claude estava expirada;
  o owner já havia autorizado prosseguir sem essa revisão quando indisponível.
