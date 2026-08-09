# Cerimônia de chaves — RF QOL 1.0

Estado: chave de lease gerada, validada e revisada pelo owner; backup e
promoção pendentes; chave de update ainda não gerada
Escopo: lease Ed25519 e update Ed25519

## Separação de papéis

| Papel | Local da privada | Uso | `key_id` esperado |
|---|---|---|---|
| Lease | segredo online exclusivo do emissor | assinar leases v2 de até 24 h | `lease-AAAA-NN` |
| Update | mídia/cofre offline, fora do servidor | assinar manifesto e procedência após gerar os bytes finais | `update-AAAA-NN` |

As privadas de lease e update não podem compartilhar arquivo, conta, backup,
permissões ou máquina operacional. Nenhuma privada entra no Git, em artefato,
log, variável persistida pelo cliente ou pacote de suporte.

## Participantes e evidência mínima

- operador da chave;
- testemunha/revisor diferente do operador;
- owner que autoriza a promoção;
- data, ambiente, ferramenta e versão;
- SHA-256 das chaves públicas;
- `key_id` de cada papel;
- local de custódia e procedimento de recuperação, sem registrar segredos.

## Sequência da cerimônia

1. Usar máquina limpa e atualizada, desconectada para a chave de update.
2. Gerar dois pares Ed25519 independentes com CSPRNG do sistema.
3. Exportar somente as públicas em base64url sem padding.
4. Confirmar que cada privada valida apenas a própria pública.
5. Guardar a privada de update offline em duas cópias cifradas e controladas.
6. Instalar a privada de lease somente no segredo do emissor de staging.
7. Substituir no cliente os identificadores `*-production-pending` pelas
   públicas aprovadas.
8. Rodar os vetores de lease, manifesto, papel trocado e assinatura alterada.
9. Registrar a ata sem incluir privada, seed, senha ou conteúdo do cofre.
10. Destruir arquivos temporários e verificar que não ficaram em histórico,
    terminal, cache, backup ou artefato.

## Assinatura de código do Windows

Por decisão do owner, o RF QOL 1.0 não usa certificado Authenticode. Executável
e instalador permanecem `NotSigned`; metadados e logo Karvalho não constituem
prova criptográfica de origem. O Windows poderá exibir `Publicador desconhecido`
e alertas do SmartScreen. A confiança do conteúdo depende da chave Ed25519 de
update pinada no programa, manifesto/procedência assinados, tamanho e SHA-256.

## Rotação e incidente

- Rotação normal: distribuir `current + next` em versão assinada pela chave de
  update atual; depois remover a antiga em outra versão aprovada.
- Privada de lease comprometida: revogar o segredo online, ativar a próxima
  pública já pinada e reduzir o impacto ao TTL máximo de 24 h.
- Privada de update comprometida: bloquear o feed e distribuir instalador
  manual por canal oficial, com hashes publicados por canal independente; não
  confiar em rotação publicada pela chave exposta.

## Gates automáticos existentes

`app.license.validate_release_configuration()` confirma a pública definitiva
de lease. `app.updater.validate_release_configuration()` continua impedindo o
build de release enquanto `update-production-pending` estiver presente. O
fluxo local nunca gerou nem guardou a privada correspondente à pública
placeholder de update.

## Registro parcial — lease-2026-01

- geração autorizada pelo owner em 09 ago 2026;
- algoritmo: Ed25519 por CSPRNG do sistema via `cryptography 46.0.7`;
- pública base64url pinada no cliente;
- SHA-256 da pública:
  `e16848fbb9d53036651dc5cdfed20d47cc29cd10240ec1317434c5b66a40dc42`;
- autoteste de assinatura e verificação: aprovado;
- ensaio Docker efêmero 8789: licença Base+Boss aceita pelo cliente com a
  pública pinada, PvP negado e licença descartável revogada;
- privada sob ACL restrita ao operador, Administradores e SYSTEM;
- não instalada no emissor de produção;
- Carlos confirmou como revisor humano o `key_id`, a pública, o SHA-256, os
  controles de acesso e a ausência de promoção em 09 ago 2026;
- cópia de recuperação segura: pendente;
- chave `update-2026-01`: não gerada; deve usar ambiente offline separado.

O registro local sanitizado está fora dos repositórios em
`K:\MCP\_ceremony\rf-qol-1.0\lease-2026-01\ceremony-evidence.json`.
Ele não contém a privada.
