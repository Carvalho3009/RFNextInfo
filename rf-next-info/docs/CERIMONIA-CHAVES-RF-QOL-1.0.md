# Cerimônia de chaves — RF QOL 1.0

Estado: procedimento preparado; chaves de produção ainda não geradas
Escopo: lease Ed25519, update Ed25519 e Authenticode Karvalho

## Separação de papéis

| Papel | Local da privada | Uso | `key_id` esperado |
|---|---|---|---|
| Lease | segredo online exclusivo do emissor | assinar leases v2 de até 24 h | `lease-AAAA-NN` |
| Update | mídia/cofre offline, fora do servidor | assinar manifesto após Authenticode | `update-AAAA-NN` |
| Authenticode | provedor/cofre do certificado Karvalho | assinar EXE e instalador | subject/thumbprint registrados na ata |

As privadas de lease e update não podem compartilhar arquivo, conta, backup,
permissões ou máquina operacional. Nenhuma privada entra no Git, em artefato,
log, variável persistida pelo cliente ou pacote de suporte.

## Participantes e evidência mínima

- operador da chave;
- testemunha/revisor diferente do operador;
- owner que autoriza a promoção;
- data, ambiente, ferramenta e versão;
- SHA-256 das chaves públicas e do certificado público;
- `key_id`, subject, issuer, serial, thumbprint e validade do certificado;
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

## Authenticode

O certificado real somente entra após G2. Registrar o subject e thumbprint
aprovados e então tornar a verificação do cliente mais estrita que a busca
temporária pelo nome `Karvalho`. O build de release exige SHA-256, timestamp
RFC 3161 e `signtool verify /pa /tw` no executável e no instalador.

## Rotação e incidente

- Rotação normal: distribuir `current + next` em versão assinada pela chave de
  update atual; depois remover a antiga em outra versão aprovada.
- Privada de lease comprometida: revogar o segredo online, ativar a próxima
  pública já pinada e reduzir o impacto ao TTL máximo de 24 h.
- Privada de update comprometida: bloquear o feed e distribuir instalador
  manual com Authenticode; não confiar em rotação publicada pela chave exposta.
- Certificado comprometido: interromper release, revogar no emissor e repetir a
  validação pública com o novo certificado.

## Gates automáticos existentes

`app.license.validate_release_configuration()` e
`app.updater.validate_release_configuration()` impedem build de release
enquanto chaves `-pending` estiverem presentes. O fluxo local nunca gerou nem
guardou as privadas correspondentes às públicas placeholder.
