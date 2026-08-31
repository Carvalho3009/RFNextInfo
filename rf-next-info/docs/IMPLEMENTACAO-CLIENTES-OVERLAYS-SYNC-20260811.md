# RF QOL — clientes, overlays e sincronização de identidades

Data: 11 ago 2026  
Estado: implementado e validado localmente; não publicado

## Escopo

- definir manualmente o UID por duplo clique em Cliente A, Cliente B ou Emulador;
- remover o botão separado de UID e a função de renomear clientes;
- limpar o alvo PvP após 3 segundos sem nova confirmação;
- reduzir os overlays para 340 px de largura e mantê-los como janelas independentes
  quando a janela principal for minimizada;
- identificar os overlays pelo personagem confirmado vinculado à leitura;
- priorizar o cliente ativo no overlay de Boss;
- separar os jogadores do Boss em colunas por guilda;
- sincronizar UID, personagem e guilda entre programas por meio do site;
- tornar explícito quando nenhuma Farm encerrada foi selecionada para envio.

## Contrato visual de nomes e UID

Os slots mantêm os nomes fixos `Cliente A`, `Cliente B` e `Emulador 1–5`.
Quando o personagem é conhecido, o programa acrescenta seu nome capturado ao
rótulo. O duplo clique abre a seleção entre detecção automática e UIDs já
confirmados; o vínculo não permite usar o mesmo UID simultaneamente em dois
clientes. Nos overlays, a origem continua sendo exclusivamente o personagem
confirmado vinculado ao UID/rota.

## Retenção PvP

Jogadores próximos e o último alvo PvP deixam de ser exibidos após 3 segundos
sem confirmação do stream. A regra é aplicada no resumo de combate e novamente
no overlay, evitando que uma atualização antiga volte a mostrar o nome.

Evolução local posterior: o overlay único foi dividido em Alvo atual,
Próximos hostis e Próximos não hostis. O status manual do Banco PvP define
somente a separação das listas próximas; não altera qual alvo foi confirmado
pela captura.

## Banco compartilhado de identidades

O programa mantém `character_observations` no banco local de conhecimento. O
site consolida os campos sanitizados nas tabelas:

- `observed_characters`: estado mais recente por `character_uid`;
- `observed_character_sources`: primeira e última observação por Profile, sem
  expor a origem na resposta;
- `observed_mobs`: catálogo observado já previsto pelo cliente.

`POST /api/import/observations` exige token de Profile, lease v2 válida e chave
de idempotência. A resposta devolve até 5.000 identidades consolidadas. O
programa mescla apenas campos decodificados e usa guilda conhecida para
recalcular a divisão de DPS do Boss.

Limite de privacidade: o contrato não aceita nem devolve payload bruto, token,
senha ou opcode `0x0101`.

## Farm

O log da instalação testada mostrou `subsessions=0` e nenhuma tentativa de
envio. Portanto, naquela sessão não havia uma Farm encerrada para o site
importar. O caminho de importação foi mantido e validado de ponta a ponta:

1. criar/iniciar uma subsessão de Farm no programa;
2. encerrá-la;
3. selecioná-la na lista;
4. usar **Enviar selecionadas**;
5. conferir o registro no Histórico/Farm do mesmo Profile no site.

Quando nada estiver selecionado, o programa agora informa
`Nenhuma Farm encerrada foi selecionada para envio.`

## Validação local

- compilação do programa e do servidor;
- suíte `unittest` do programa: 229 testes aprovados;
- testes Qt reais para UID por duplo clique, overlays e Boss por guilda;
- autoteste integral do servidor com importação e leitura duplicada de
  observações;
- `git diff --check` nos dois worktrees.

## Separação dos ambientes

- programa: `K:\MCP\_worktrees\rf-qol-security-implementation\rf-next-info`;
- site: `K:\MCP\_worktrees\rf-next-qol-site-sync\rf-next\app`.

Nenhum arquivo da instalação atual ou da produção foi substituído nesta etapa.
