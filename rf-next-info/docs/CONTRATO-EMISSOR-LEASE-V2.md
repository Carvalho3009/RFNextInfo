# Contrato do emissor de licença — RF QOL lease v2

Estado: cliente, site e emissor implementados e integrados em staging isolado;
chaves de produção, cutover e publicação continuam pendentes.

Implementação do emissor: `K:\MCP\_worktrees\rf-licenca-security-r1`.
Homologação: contêiner `rf-licenca-staging-api-1`, somente em
`127.0.0.1:8788`, com dados e chaves efêmeros separados da produção.

## Identidade

- produto: `rf-qol`
- audience: `rf-qol-windows`
- issuer: `rflicenca.karvalho.dev.br`
- chave de acesso nova: `RFQ-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX`
- `installation_id`: UUID canônico gerado pelo cliente
- TTL offline máximo: 24 horas
- próxima tentativa online: no máximo 6 horas após emissão

Licenças `KRV-*`, lease v1 e licenças do produto anterior devem falhar
fechado. A chave de acesso nunca é devolvida, persistida pelo cliente ou
incluída em logs de auditoria.

## `POST /api/v2/activate`

Requisição:

```json
{
  "license_key": "RFQ-...",
  "installation_id": "uuid",
  "app_version": "1.0.0",
  "product": "rf-qol",
  "audience": "rf-qol-windows"
}
```

Resposta `200`: `{"lease":"payload_base64url.assinatura_base64url"}`.

O emissor valida produto, audience, formato, status, limite de ativações e
expiração do entitlement antes de vincular a instalação. Repetir a mesma
ativação deve ser idempotente; conflito com outra instalação usa erro explícito
sem revelar dados da licença.

## `POST /api/v2/validate`

Requisição:

```json
{
  "lease": "...",
  "app_version": "1.0.0",
  "product": "rf-qol",
  "audience": "rf-qol-windows"
}
```

Resposta ativa: nova lease v2, com novo `lease_id`, mesma instalação e janela
de no máximo 24 horas. Revogada, desabilitada ou expirada retorna 401/403; o
cliente apaga imediatamente a lease ativa. Indisponibilidade usa 5xx/timeout e
nunca é convertida em autorização pelo site.

## Claims assinados

O payload contém exatamente os campos normativos da SPEC: `v`, `iss`,
`product`, `aud`, `key_id`, `lease_id`, `license_id`, `installation_id`,
`issued_at`, `next_check_at`, `valid_until`, `entitlement_expires_at`,
`features` e `connection_limits`. Datas
são ISO-8601 UTC com fuso. Deve valer:

`issued_at <= next_check_at <= valid_until <= entitlement_expires_at`

e também:

- `next_check_at - issued_at <= 6 h`;
- `valid_until - issued_at <= 24 h`.

`features` é uma lista em ordem canônica. `base` é obrigatória e pode ser
acompanhada por `monitor-pve`, `monitor-pvp` e `monitor-boss`. Valores
desconhecidos, duplicados ou fora dessa ordem invalidam a lease.

`connection_limits` contém exatamente `pc` e `emulators`. Os únicos valores
aceitos são `{"pc":2,"emulators":1}` e `{"pc":2,"emulators":5}`.
Esse direito é independente de `features` e da quantidade de instalações.

## Introspecção para o site

O serviço usado por `rf-next/app/server.py` deve devolver, no mínimo:

```json
{
  "active": true,
  "v": 2,
  "product": "rf-qol",
  "aud": "rf-qol-windows",
  "installation_id": "uuid",
  "valid_until": "UTC",
  "features": ["base", "monitor-pvp"]
}
```

O site já rejeita ausência, `active != true`, v1, produto/audience divergentes
e instalação diferente do envelope enviado. Timeout ou resposta inválida é
negação, não fallback.

## Erros, limite e auditoria

- `400`: formato inválido;
- `401/403`: licença inativa, expirada, revogada ou vínculo negado;
- `409`: conflito de ativação que o usuário pode resolver;
- `429`: limite por IP + licença derivada/installation_id, com `Retry-After`;
- `5xx`: falha interna sem detalhe sensível.

A auditoria registra evento, horário, resultado, versão, product/audience e
identificadores pseudonimizados. Nunca registra chave de acesso, lease completa,
privada, IP bruto de longo prazo ou payload do jogo.

## Vetor público

`tests/fixtures/lease-v2-valid.json` é um vetor determinístico com pública de
teste e horário de verificação fixo. A privada foi descartada. Ele serve para
compatibilidade cruzada; casos inválidos são derivados em memória nos testes.
