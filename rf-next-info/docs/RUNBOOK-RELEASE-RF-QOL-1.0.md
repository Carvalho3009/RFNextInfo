# Runbook de release — RF QOL 1.0

Estado: preparado; G4 de release pendente. Em 12/08/2026, o owner autorizou
somente atualizar a branch pública de download, sem criar GitHub Release.

## Pré-condições

- branch aprovada, commit limpo e revisão concluída;
- emissor/site v2 validados em staging;
- chave pública definitiva de lease instalada;
- NSIS 3.12 disponível;
- `app.updater.UPDATE_MODE` igual a `manual`;
- matriz local aprovada pelo owner; validação externa foi dispensada.

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
5. Confirmar `update_mode=manual` na procedência.
6. Confirmar que `RF QOL.exe` e `RF QOL Setup 1.0.0.exe` permanecem
   `NotSigned`, conforme a decisão do owner.
7. Verificar que `release-provenance.json`, `sbom-python.json`, lock e
   `SHA256SUMS.txt` correspondem aos bytes finais.
8. Confirmar que `update-manifest.json`, `rollback-manifest.json` e
   `release-provenance-signature.json` não foram gerados no modo manual.
9. Confirmar que o NSIS exibe os Termos de Uso 1.0 e impede o avanço até o
   usuário marcar “Li e aceito os Termos de Uso”.

Atualização e rollback automáticos estão desativados. O programa abre o Discord
oficial para avisos; o usuário baixa e executa manualmente o instalador completo.
Para voltar de versão, usar somente um instalador oficialmente indicado como
compatível. O programa não baixa nem inicia executáveis.

Se o owner reativar atualização automática no futuro, mudar `UPDATE_MODE` para
`automatic`, concluir `update-2026-01`, repetir a matriz de update/rollback e
então fornecer ao build:

```powershell
$env:RFQOL_UPDATE_KEY_ID = 'update-2026-01'
$env:RFQOL_UPDATE_PRIVATE_KEY = '<MIDIA_PRIVADA>:\RF-QOL\update-2026-01.private.pem'
$env:RFQOL_ROLLBACK_INSTALLER = '<INSTALADOR_ANTERIOR>'
$env:RFQOL_ROLLBACK_VERSION = '<VERSAO_ANTERIOR>'
$env:RFQOL_ROLLBACK_SEQUENCE = '<SEQUENCIA_ANTERIOR>'
.\packaging\build.ps1 -Release
```

Versão e sequência novas são lidas de `app.main.VERSION` e
`app.main.RELEASE_SEQUENCE`; o build não aceita valores externos divergentes.

Publicar na release nova o instalador anterior e esse manifesto dedicado. O
cliente recusa a atualização se o par não corresponder exatamente à versão e
à sequência atualmente instaladas.

Antes do RC, executar o ensaio sem elevação com `packaging/test-installer.ps1`.
Esse modo não cria registro/atalhos, usa pasta temporária e
`RFQOL_SELF_TEST=1`; ele confirma `NotSigned` e comprova instalação, autoteste
pós-instalação e desinstalação sem
alterar o `AppId`, `%ProgramFiles%` ou `%ProgramData%` da futura release.

No modo automático futuro, o manifesto volta a ser o último artefato assinado.

## Matriz de RC

- instalação do zero sem importar licença/estado da linha anterior;
- aceite obrigatório e leitura dos Termos de Uso 1.0 antes da instalação;
- ACL de `%ProgramData%\Karvalho\RF QOL` somente Administradores/SYSTEM;
- primeira ativação RFQ, renovação, offline <24 h, limite de 24 h e revogação;
- bloqueio de captura, leitura, monitores, exportação e envio sem lease;
- preservação dos PCAPs ao perder autorização durante captura;
- link exato `https://discord.gg/D3hhdMgkj` no navegador padrão;
- controles automáticos desativados e botão apontando ao Discord oficial;
- `SHA256SUMS.txt` correspondendo ao instalador final;
- varredura de logs, banco, PCAP/diagnóstico e staging por segredos proibidos.

Rollback é manual e não aparece como ação disponível. Não orientar downgrade
sem confirmar compatibilidade de dados e preservar um backup íntegro do banco.

## Publicação (somente após G4)

1. Publicar instalador, `SHA256SUMS.txt`, SBOM e procedência aprovados.
2. Baixar novamente da superfície pública.
3. Repetir SHA-256, confirmação `NotSigned` e self-test no download.
4. Confirmar que o programa não consulta feed nem oferece download automático.
5. Ativar licença nova real e validar upload v2; comprovar rejeição de lease v1.
6. Registrar hashes, horários, responsáveis e URLs na ata final.

## Abortar sem impacto

Qualquer falha descarta os artefatos candidatos. Não alterar feed, emissor de
produção ou instalação dos usuários. A beta 3.0.11 permanece independente.
