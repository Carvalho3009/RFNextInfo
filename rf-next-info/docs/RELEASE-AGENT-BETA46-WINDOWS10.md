# Companion 2.0.0-beta.46 — estabilidade do Agent

Sequência: 56. Escopo autorizado: implementar as correções reproduzidas na
auditoria da beta.45 e publicar no atualizador. Sem alterações no receptor,
esquema remoto, decoder canônico ou instalação em uso.

## Correções implementadas

- Remontagem TCP considera a volta da sequência de 32 bits, SYN, RST e FIN,
  retransmissões e encerramento fora de ordem, isoladamente por conexão.
- Rotas diretas usam portas remotas estáveis; relays mantêm suas portas locais,
  inclusive com dois clientes do mesmo executável usando caminhos diferentes.
  A troca de filtros substitui a geração anterior e verifica o teto nativo antes
  de parar a captura. Não implica homologação do ExitLag.
- Falhas de controlador/consumidor deixam de aparecer como captura ativa.
  Recuperação do backend conserva a sessão e as identidades; encerramento
  incompleto mantém recursos para uma tentativa segura, sem consumidor duplicado.
- Limpeza ETW tenta fechar trace e filtros próprios mesmo após outro erro;
  CloseTrace pendente mantém o callback vivo até o consumidor terminar.
- Pacotes aceitos são drenados antes de encerrar o decoder; atraso de drenagem
  é informado e impede nova captura sobre o worker antigo. A ponte tem espera
  limitada e informa worker interrompido, em vez de aguardar indefinidamente.
- Ocupação temporária do SQLite deixa de bloquear permanentemente a entrega.
  Corrupção e falhas permanentes continuam bloqueadas, sem apagar a fila.
- Rede de autorização/sincronização não mantém o lock da saúde do runtime;
  o cache de autorização conserva o vencimento original. O worker de comandos
  ainda pode aguardar o timeout HTTP, sem congelar a janela Qt.
- Erros e leituras antigas ficam visíveis; diagnóstico inclui horário da amostra,
  defasagem e plataforma. Logs usam rotação de 2 MiB com três backups.
- Compactação e alimentação do remontador usam a mesma proteção de concorrência.
  Saúde informa que as perdas nativas ETW não são mensuradas, em vez de inferir
  ausência de perdas a partir dos contadores herdados.

## Validação antes do pacote

- `tests.test_agent_stability`: 18 testes sintéticos, aprovados. Incluem dois
  clientes, reuso de conexão, reinício de captura sem nova sessão, múltiplos
  ciclos, 200 mudanças de portas diretas, 40 mudanças de relay, cleanup parcial,
  banco ocupado, erro de interface, drenagem e leitura de saúde durante HTTP.
- Regressão completa: 655 testes em 67,753 s, sem falhas, dois skips opcionais.
- Replay privado de equipamentos executado separadamente: os 12 testes de
  `tests.test_equipment_delivery` passaram, incluindo a captura autorizada
  anteriormente disponível. Nenhum pacote bruto foi incorporado ao repositório.
- Perfil de release e `git diff --check` aprovados. Ensaio do instalador,
  self-test empacotado, hashes e assinaturas constam da evidência do artefato
  publicado, não são inferidos destes testes de código.

## Limites que permanecem explícitos

Não houve ensaio físico no Windows 10 afetado, sessão de muitas horas,
suspensão/retomada, logon com inicialização automática/UAC, disco cheio ou
interrupção do instalador. RAM é orçamento adaptativo, não teto rígido. A fila
tem capacidade finita e novas admissões podem falhar ao esgotá-la. Estatísticas
de perda ETW e otimização do callback continuam dependendo de medição real.
Pktmon ocupado ou com propriedade ambígua continua bloqueado com segurança;
não se encerra uma captura desconhecida para forçar a recuperação.

O script `audit_windows10_beta45.py` é preservado como prova histórica e aceita
somente aquele baseline; os testes de comportamento corrigido ficam na suíte.

## Publicação e reversão

Canal: `download/rf-qol-agent-beta`; artefato versionado:
`download/rf-qol-agent-2.0.0-beta.46`. Instalador sem Authenticode por decisão
do proprietário; manifesto e procedência Ed25519 com a chave existente.
Não há novas dependências, drivers, bypass de antivírus ou migração de banco.

Rollback disponível: preservar artefato beta.45 e feed anterior no commit
`52d0e7138175206ead8e9bb1f92c595f3551629d`. Restaurar o feed suspende a oferta
nova; não faz downgrade automático de quem já instalou. A instalação anterior
depende de consentimento, preservando identidade, configuração e outbox.

Estado: implementado e publicado em 08/09/2026. Pacote/publicação registrados
em `build-evidence.json` e `provenance.json` do download.
Próximo gate externo: homologação no Windows 10 22H2 x64 afetado.
Rotinas usadas: operar-mcp para evidências/gates; Ponytail para reutilizar os
componentes existentes e a biblioteca padrão. Custo real: desconhecido.

## Evidência da publicação

- Código empacotado: `2209391b1355c351cffcd04200060cbe6b1210aa`.
- PR restrito às mudanças da beta.46: https://github.com/Carvalho3009/RFNextInfo/pull/38.
- Artefato: `575104a087db4223f6c519490aef51ca54ffbe7f`.
- Canal: `2e93d704da322a7e66e7c4968e9f51d3e4e1cd72`.
- Instalador: `RF-Next-Companion-Setup-2.0.0-beta.46.exe`, 35.799.296 bytes.
- SHA-256: `94e943aff606efc3071e811129735a531a4551433f787e6acb4886412ff35478`.
- Download público: https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/download/rf-qol-agent-2.0.0-beta.46/RF-Next-Companion-Setup-2.0.0-beta.46.exe.
- Autoteste empacotado aprovado: dois clientes, três sessões isoladas, sem rede.
- Ensaio isolado de instalação, migração do executável legado e remoção aprovado.
- Doze módulos do executável comparados com o código validado, incluindo entrada,
  decoder, remontagem, captura, entrega e perfil de versão.
- Instalador público baixado pelo próprio código do atualizador; tamanho/hash,
  manifesto Ed25519 e procedência Ed25519 aprovados após download.
- Feed público oferece beta.46 às sequências 51–55 e não repete a oferta para 56.
- Beta.45 preservada na mesma referência pública; sem alteração da instalação
  atual, do receptor ou do banco de produção. Nenhuma homologação física inferida.
