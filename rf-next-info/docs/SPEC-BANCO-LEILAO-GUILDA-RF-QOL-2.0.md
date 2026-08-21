# RF QOL — Banco de Leilão da guilda

Status: a versão 2.0 prepara o contrato e o envio sanitizado do programa. O
banco compartilhado, a leitura consolidada e os alertas de undercut continuam
como evolução de site/2.1 e não são ativados sem validação do endpoint remoto.

## Objetivo da 2.1

Consolidar as vendas próprias confirmadas dos membros para reduzir conflitos de
preço dentro da guilda. O recurso apenas informa e alerta: nunca cadastra,
cancela ou bloqueia uma venda dentro do jogo.

## Fontes confirmadas

O decoder canônico já fornece:

- `0x1D07`: lista de vendas próprias;
- `0x1D09`: lista própria de liquidação;
- `0x1D0D` e `0x1D11`: cadastro e recadastro aceitos;
- `0x1D0F`: cancelamento aceito;
- `0x1D15`: liquidação aceita;
- `0x1D1B`: notificação de venda.

Os detalhes confirmados incluem índice do item, quantidade, refino, preço por
unidade e tempos do protocolo. Respostas com `ret != 0` não mudam o estado.

## Projeção local implementada

`core/auction_sales.py` reconstrói, em ordem, o estado `active`, `sold`,
`cancelled` ou `settled`. A consulta do SQLite é isolada por sessão e personagem.

O snapshot público contém somente:

- `listing_id` opaco, derivado com HMAC e chave local protegida;
- servidor, item, nome resolvido, refino, quantidade e preço unitário;
- preço de liquidação e tempos do protocolo quando disponíveis;
- estado, instante de observação e confiança confirmada.

Não saem `exchange_index`, `account_id`, `pc_id`, UID do item, opções/talics,
payload bruto, fluxo, token, ticket ou `0x0101`.

O cálculo local de undercut compara apenas anúncios ativos com o mesmo servidor,
item e refino. O resultado informa o menor preço e a diferença; não impede ação.

## Contrato de envio preparado na 2.0

Endpoint: `POST /api/import/auction-bank` autenticado pelo token do
Profile. O site deve associar cada envio ao Profile autenticado, sem aceitar
identidade de usuário informada pelo corpo.

Envelope candidato:

```json
{
  "metadata": {
    "schema_version": 1,
    "session_id": "sessao-local",
    "privacy": "decoded-fields-only; no account, character or exchange ids"
  },
  "listings": [],
  "transactions": []
}
```

Regras obrigatórias:

- limite de tamanho e quantidade por envio;
- validação estrita de servidor, item, refino, quantidade, preço e estado;
- idempotência por Profile + `snapshot_id` + `listing_id`;
- atualização monotônica de estado; snapshot antigo não reativa venda encerrada;
- rejeição integral ou resultado por item explícito, nunca sucesso ambíguo;
- auditoria de criação, atualização, cancelamento e remoção;
- API de leitura separada da API de importação.

## Decisão de arquitetura para undercut

O cálculo principal deve ficar no site. Somente o site enxerga, ao mesmo tempo,
os anúncios enviados pelos vários membros e consegue aplicar permissões da
guilda, idempotência, expiração e auditoria. O programa mantém apenas a projeção
local e, futuramente, apresenta a resposta consolidada recebida do site.

Fluxo recomendado:

1. o programa envia listagens confirmadas e sanitizadas;
2. o site consolida por guilda, servidor, item e refino;
3. o site calcula o menor preço ativo e conflitos concorrentes;
4. o programa recebe somente avisos autorizados e os exibe;
5. nenhum componente cadastra, cancela ou altera uma venda no jogo.

Fazer o cálculo apenas no programa seria incompleto porque ele não conhece os
anúncios dos outros computadores. Duplicar toda a regra nos dois lados também
criaria divergência; por isso o site é a fonte consolidada e o programa é o
cliente de apresentação.

## Visibilidade e anti-undercut

Padrão recomendado, ainda sujeito à aprovação do owner:

- leitura somente para membros ativos da mesma guilda;
- edição manual apenas pelo dono da listagem ou líder autorizado;
- vendedor exibido pelo nome do Profile do site, não por ID do protocolo;
- menor preço calculado apenas entre anúncios ativos do mesmo servidor, item e
  refino;
- alerta se a intenção ou venda nova ficar abaixo do menor preço da guilda;
- venda externa ao Banco não é classificada como infração;
- nenhuma automação ou punição.

## Gates da 2.1 antes do site

O owner precisa definir:

1. quais cargos podem ver preço, quantidade e vendedor;
2. se líderes podem editar ou somente ocultar registros de outros membros;
3. retenção de vendas encerradas e trilha de auditoria;
4. prazo para considerar anúncio ativo sem nova confirmação;
5. se haverá intenção manual `planned` antes do cadastro no jogo;
6. política para saída do membro da guilda e troca de Profile.

Sem essas decisões, ficam bloqueados schema do banco do site, rotas remotas e
interface compartilhada. Na 2.0, a projeção local existente deve apenas ser
preservada, sem antecipar essas permissões ou receber evolução funcional.

## Critérios de aceite da 2.1

- eventos de erro não alteram a lista;
- o ciclo cadastro → venda → liquidação é monotônico;
- cancelamento e venda desconhecidos não expõem registros incompletos;
- snapshots de personagens diferentes não se misturam;
- nenhum identificador proibido aparece no JSON público;
- o mesmo anúncio mantém `listing_id` com a mesma chave local;
- o alerta usa apenas anúncios ativos comparáveis e nunca bloqueia a venda;
- reenvio idêntico não cria duplicata no site.

## Rollback

A projeção é somente leitura sobre eventos já persistidos e não cria tabela
nova. O rollback remove o módulo e sua consulta, preservando captura, decoder,
Mercado atual e histórico existente.
