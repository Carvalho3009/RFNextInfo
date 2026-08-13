# Correções de Banco PvP, Inventário e Envios — RF QOL 1.0

Data: 12 ago 2026
Estado: programa implementado e validado localmente; servidor e proxy
publicados em 12 ago 2026; instalador manual 1.0.1 publicado em branch exclusiva
de download em 12 ago 2026

## Banco PvP

- Guilda pode ser alterada manualmente mesmo quando já existe.
- Status aceita Aliado, Inimigo, Neutro e Ignorar.
- O decoder fornece `guild_id` nos jogadores e listas de guildas inimigas e
  aliadas; o programa cruza esses eventos para preencher guilda e status
  observados automaticamente.
- O Banco PvP exibe Classe e Rover. O programa envia os códigos observados do
  biosuit e do rover; a classe é derivada do biosuit pelo catálogo oficial e o
  nome do rover segue o idioma configurado para os dados do jogo.
- Biosuit e rover percorrem o mesmo fluxo moderado: programa para Banco
  Temporário, aprovação no site e Banco Final para os programas.
- Guilda ou status alterados manualmente têm prioridade sobre novas observações.
- Ignorar é enviado como proposta temporária e só passa a valer nos demais
  programas depois de aprovado no Banco Final; no programa que fez a edição,
  o UID fica oculto enquanto a proposta local estiver pendente.
- Uma edição apenas marca o registro como pendente.
- Envio automático usa intervalo configurável de 1 a 60 minutos, com padrão
  de 5 minutos; ele envia somente as pendências locais ao Banco Temporário.
- `Enviar ao site` envia as alterações pendentes e não mescla o Banco Final
  devolvido pelo POST legado.
- `Receber do site` consulta somente o Banco Final aprovado e o mescla no banco
  local, sem criar lote ou proposta no Banco Temporário.
- `Atualizar` permanece estritamente local: relê o SQLite e redesenha a tabela.
- O envio do programa alimenta somente o Banco Temporário e suas propostas.
- O servidor devolve exclusivamente a revisão publicada do Banco Final,
  inclusive registros ignorados, e essa revisão substitui a identidade local.
- A tabela permite filtrar por texto e status, mover e redimensionar colunas e
  preservar a organização escolhida.
- Cada linha possui uma caixa de seleção. Os UIDs marcados podem receber em
  lote somente guilda, somente status ou ambos; cada UID alterado fica pendente
  para o próximo envio.
- O cliente aceita até 8 MiB de resposta JSON do Banco Final, evitando truncar
  bancos compartilhados maiores e preservando um limite de segurança.

## Inventário

- A reconstrução usa o UID da instância dentro do personagem e tipo do item.
- Registros antigos sem UID mantêm o fallback por tipo e slot.
- Clique direito permite escolher manualmente uma das seis categorias.
- A escolha é persistida por código do item nas preferências locais e no
  inventário sanitizado enviado ao site.

## Envios

- Botões por cliente exibem o mesmo rótulo Cliente/Emulador - Personagem.
- Inventário possui envio próprio por cliente.
- Enviar tudo executa Personagem, Inventário, Codex e Memory Chips para o
  cliente escolhido; ausência de dados de Codex/Memory Chips é ignorada, mas
  erros reais interrompem e são informados.
- O site sanitiza e persiste o inventário recebido no personagem por UID.
- Alertas de proximidade permanecem somente no programa e não possuem envio
  ou configuração remota no site.

## Limites

- Mercado continua geral e não faz parte de Enviar tudo do cliente.
- A categoria manual não altera os dados oficiais do jogo; o site a preserva
  como classificação manual daquele inventário.
- O instalador 1.0.1 foi publicado somente na branch órfã de download
  `download/rf-qol-1.0.1`; não houve GitHub Release.

## Aceite

- snapshots reais com slots repetidos preservam todas as instâncias por UID;
- guilda existente pode ser substituída e sincronizada pelo timestamp próprio;
- Ignorar é propagado e ocultado em outro cliente após sincronização;
- nenhuma edição dispara upload imediato;
- intervalo, organização das colunas, categoria manual e rótulos persistem
  após nova leitura;
- filtros não alteram dados e a edição em lote atinge somente as linhas
  selecionadas;
- enviar não recebe o Banco Final e receber não cria propostas temporárias;
- classe e rover só são compartilhados depois da aprovação das respectivas
  propostas, e a revisão final devolve seus códigos aos demais programas;
- inventário e tudo enviam somente o cliente selecionado;
- cliente e servidor passam testes dedicados e regressão completa.

## Validação local

- 238 testes do RF QOL aprovados.
- Self-test do decoder aprovado com `guild_id` e relações inimiga/aliada.
- Self-test do servidor aprovado com dados canônicos locais.
- Banco real de diagnóstico reconstruído com 255 itens em um personagem e 236
  em outro, preservando instâncias que compartilham slot.
- Compilação Python e verificação de diferenças sem erros.
- Na validação original, nenhum instalador, push, deploy ou alteração de
  produção havia sido realizado.

## Publicação parcial — 12 ago 2026

- o proxy público passou a liberar `/api/import/observations` para autenticação
  por token do Profile, sem sessão do Authentik;
- o site publicado preserva a categoria manual do inventário;
- o site publicado recebe biosuit e rover no Banco Temporário, apresenta as
  respectivas propostas para aprovação e expõe Classe e Rover no Banco Final;
- observações do programa ficam no Banco Temporário, inclusive propostas de
  status, e a resposta da API contém somente o Banco Final publicado;
- o banco real foi migrado com backup, `integrity_check=ok` e nenhuma violação
  de chave estrangeira;
- alertas de proximidade não são enviados ao site;
- o programa atualizado foi empacotado como `RF QOL Setup 1.0.1.exe` em uma
  pasta de entrega isolada.

## Instalador 1.0.1 — 12 ago 2026

- versão do programa `1.0.1`, sequência interna `2`;
- 238 testes aprovados e autoteste do executável empacotado aprovado;
- ensaio isolado de instalação, autoteste pós-instalação e desinstalação
  aprovado;
- instalador e executável permanecem `NotSigned` conforme decisão do owner;
- SHA-256 do instalador:
  `D40AC86F6B2ADA7D9E00007E339AAAC5DF4EE451BFF014DE3817EC6BF3431754`;
- atualização manual; nenhum GitHub Release ou instalação sobre a versão em uso
  foi realizado;
- branch pública exclusiva `download/rf-qol-1.0.1`, commit
  `3a298c00421cf81cdf0362aaaa51444cae78579c`, contendo apenas os artefatos de
  distribuição;
- o instalador foi baixado novamente pelo link público com 48.340.379 bytes e
  o mesmo SHA-256 informado acima.

## Ampliação Classe e Rover — 12 ago 2026

- a tabela local do Banco PvP ganhou as colunas Classe e Rover;
- a classe é derivada do código do biosuit e o rover usa o catálogo PT/EN já
  adotado pelo programa;
- a migração do banco foi validada em cópia com `integrity_check=ok` e nenhuma
  violação de chave estrangeira;
- o serviço `rfnext` foi recriado isoladamente com a imagem
  `sha256:94a570b5b5ed348db2e913b46b78f9f2651538cb845227c87a96109ae54ee811`;
- backup anterior à migração:
  `rfnext-before-pvp-class-rover-20260812-120144.sqlite`, SHA-256
  `CBE592296463DE02C7DB0663CDF52199AA2B5B7A4094E9C7D697E1805EFDF5CA`;
- os contadores funcionais foram preservados e a rota pública protegida
  continuou redirecionando para o Authentik; o endpoint de observações sem
  credenciais continuou respondendo `401`.

## Instalador 1.0.2 — 12 ago 2026

- versão do programa `1.0.2`, sequência interna `3`;
- inclui envio/recebimento separados, filtros, edição em lote e organização
  persistente das colunas do Banco PvP;
- 241 testes, autoteste do executável e ensaio isolado de instalação,
  autoteste pós-instalação e desinstalação aprovados;
- instalador `NotSigned`, com 48.356.711 bytes e SHA-256
  `A38CADD5C0C37B96D08B1B1A320AED149722CC6EEB17EECBF10D137D5F6CAEFF`;
- pacote de entrega local em `K:\MCP\_staging\rf-qol-1.0.2-20260812-r1`;
- nenhum GitHub Release, branch de download, instalação sobre a versão em uso
  ou recarga do proxy foi realizado.

## Ativação do recebimento e caixas de seleção — 12 ago 2026

- a configuração ativa do gateway foi comparada semanticamente com o arquivo;
  a única diferença era a rota `/api/pvp-sync/final`;
- o Caddy foi recarregado sem reiniciar o contêiner; a rota pública passou de
  redirecionamento Authentik para JSON da API, enquanto a página normal
  permaneceu protegida;
- o recebimento autenticado real foi validado na revisão 13 com 400 personagens;
- o Banco PvP local ganhou caixas por UID e edição em lote de guilda/status;
- quatro testes focados e a regressão completa de 242 testes foram aprovados;
- essas alterações posteriores ao build 1.0.2 foram empacotadas no candidato
  local 1.0.3 descrito abaixo.

## Instalador 1.0.3 — 12 ago 2026

- versão do programa `1.0.3`, sequência interna `4`;
- inclui caixas por UID, aplicação em lote de guilda/status e o recebimento de
  respostas do Banco Final com limite seguro de 8 MiB;
- 242 testes, autoteste do executável e ensaio isolado de instalação,
  autoteste pós-instalação e desinstalação aprovados;
- instalador `NotSigned`, com 48.349.279 bytes e SHA-256
  `5A5DABE679E1DC1EC372D73EB48349BF0F7E0EF5E1C51C20600518B4D4F488E3`;
- pacote de entrega local em `K:\MCP\_staging\rf-qol-1.0.3-20260812-r1`;
- candidato gerado da árvore local ainda não consolidada em commit; não foi
  instalado sobre a versão em uso;
- publicado sem GitHub Release na branch órfã `download/rf-qol-1.0.3`, commit
  `c8f1536d0a6376fe5a209f6ec8bbac8e4a7f98b3`;
- o instalador foi baixado novamente pelo link público com 48.349.279 bytes,
  versão `1.0.3`, estado `NotSigned` e o mesmo SHA-256 informado acima.

## Hotfix do envio do Banco PvP — 12 ago 2026

- o erro `HP máximo inválido` era causado por 30 mobs com HP desconhecido
  (`max_hp=0`) incluídos indevidamente no mesmo pacote do Banco PvP;
- o envio do Banco PvP foi restringido a personagens, sem mobs ou HP;
- o cliente também normaliza HP desconhecido para `null`, inclusive para os
  registros legados já persistidos com zero;
- o servidor passou a interpretar exclusivamente `0`/`"0"` legado como HP
  desconhecido, mantendo rejeição para valores negativos, inválidos ou fora do
  limite; essa compatibilidade permite que o instalador 1.0.3 já publicado
  volte a enviar sem depender de um novo instalador;
- backup anterior ao hotfix:
  `rfnext-before-hp-null-hotfix-20260812-185729.sqlite`, 277.131.264 bytes,
  SHA-256 `B4DC177D20215A4F8D26557CF6951A763F2E1C9C281E8AB6BE88122A485D3E3E`,
  com `integrity_check=ok`;
- somente o serviço `rfnext` foi recriado, na imagem
  `sha256:20e07384e9ec3456f28a996df991fb68bc27d365d992a107604a915d6a52d90c`;
- autoteste da imagem implantada, integridade do banco e regressão completa de
  243 testes do programa foram aprovados; a API sem token permaneceu `401` e a
  página protegida permaneceu `302` para o Authentik;
- a versão instalada repetiu o envio automaticamente às 19:00:39 e confirmou
  `observation_upload_completed characters=1551`, eliminando o erro real.
