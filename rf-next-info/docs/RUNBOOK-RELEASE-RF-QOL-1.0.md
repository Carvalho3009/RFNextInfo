# Runbook de release — RF QOL 1.0

Estado: preparado; não autorizado para publicação (G4 pendente)

## Pré-condições

- branch aprovada, commit limpo e revisão concluída;
- emissor/site v2 validados em staging;
- chaves públicas de produção instaladas e placeholders removidos;
- certificado Karvalho e timestamp RFC 3161 disponíveis pelo fluxo aprovado;
- NSIS 3.12 disponível;
- Windows 10 e 11 x64 limpos para a matriz de RC;
- `RFQOL_SIGNTOOL`, `RFQOL_CERT_SHA1`, `RFQOL_TIMESTAMP_URL`,
  `RFQOL_UPDATE_PRIVATE_KEY` e `RFQOL_UPDATE_KEY_ID` fornecidos apenas ao
  processo de release.

O compilador pode ser fornecido por `RFQOL_NSIS`. A ferramenta usada no
desenvolvimento isolado é NSIS 3.12 extraído do pacote cujo SHA-256 foi
verificado pelo catálogo do Windows Package Manager. O NSIS permite uso
comercial sob as licenças zlib/libpng, bzip2 e CPLv1 aplicáveis.

## Build candidato

1. Criar `.venv313` com `packaging/bootstrap-build.ps1`; o script instala
   `requirements-lock-win-x64-py313.txt` com `--require-hashes` e valida
   conflitos. Em ambiente isolado, passar um wheelhouse aprovado.
2. Confirmar tree limpa e commit/tag candidato.
3. Rodar toda a regressão e o self-test do servidor.
4. Executar `packaging/build.ps1 -Release`.
5. Confirmar que o script recusou qualquer chave `-pending`.
6. Confirmar Authenticode e timestamp no `RF QOL.exe` e no
   `RF QOL Setup 1.0.0.exe`.
7. Verificar que `release-provenance.json`, `sbom-python.json`, lock e
   `update-manifest.json` correspondem aos bytes finais.
8. Verificar `release-provenance-signature.json` com a pública de update. A
   assinatura destacada usa contexto próprio e não altera o instalador nem o
   manifesto já assinados.

Antes de usar certificado real, executar o ensaio sem elevação com
`packaging/test-installer.ps1`. Esse modo não cria registro/atalhos, usa pasta
temporária e `RFQOL_SELF_TEST=1`; ele comprova instalação, autoteste pós-instalação e
desinstalação sem
alterar o `AppId`, `%ProgramFiles%` ou `%ProgramData%` da futura release.

O manifesto é sempre o último artefato assinado. Alterar ou reassinar o
instalador invalida o manifesto e exige gerá-lo novamente.

## Matriz de RC

- instalação do zero sem importar licença/estado da linha anterior;
- ACL de `%ProgramData%\Karvalho\RF QOL` somente Administradores/SYSTEM;
- primeira ativação RFQ, renovação, offline <24 h, limite de 24 h e revogação;
- bloqueio de captura, leitura, monitores, exportação e envio sem lease;
- preservação dos PCAPs ao perder autorização durante captura;
- link exato `https://discord.gg/D3hhdMgkj` no navegador padrão;
- update RC1 -> RC2 com manifesto/hash/AuthentiCode reverificados;
- Windows 10 e 11 x64, até dois clientes, sem injeção/hook;
- varredura de logs, banco, PCAP/diagnóstico e staging por segredos proibidos.

Rollback permanece indisponível na interface até existir instalador anterior
assinado, manifesto original e compatibilidade de schema declarada. Não liberar
1.0 afirmando rollback automático antes desse teste real.

## Publicação (somente após G4)

1. Publicar instalador, manifesto, SBOM, procedência, assinatura destacada e
   hashes aprovados.
2. Baixar novamente da superfície pública.
3. Repetir SHA-256, Ed25519, Authenticode `/pa /tw` e self-test no download.
4. Confirmar feed estável e ausência de draft/prerelease indevido.
5. Ativar licença nova real e validar upload v2; comprovar rejeição de lease v1.
6. Registrar hashes, horários, responsáveis e URLs na ata final.

## Abortar sem impacto

Qualquer falha descarta os artefatos candidatos. Não alterar feed, emissor de
produção ou instalação dos usuários. A beta 3.0.11 permanece independente.
