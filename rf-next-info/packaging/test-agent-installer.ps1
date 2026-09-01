param(
    [Parameter(Mandatory = $true)][string]$SourceDir,
    [string]$Nsis = $env:RFQOL_NSIS,
    [string]$EvidenceRoot = ''
)

$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
$Python = if ($env:RFQOL_BUILD_PYTHON) {
    $env:RFQOL_BUILD_PYTHON
} else {
    Join-Path $Project '.venv313\Scripts\python.exe'
}
if (-not $Nsis) {
    $Nsis = 'K:\MCP\_tools\nsis-3.12\portable\makensis.exe'
}
if (-not (Test-Path -LiteralPath $Nsis -PathType Leaf)) {
    throw 'Compilador NSIS não encontrado.'
}
$SourceDir = [IO.Path]::GetFullPath($SourceDir)
if (-not (Test-Path -LiteralPath (Join-Path $SourceDir 'RF Next Companion.exe'))) {
    throw 'Pacote portátil do Agent não encontrado.'
}
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path ([IO.Path]::GetTempPath()) (
        'rf-qol-agent-installer-smoke-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    )
}
$EvidenceRoot = [IO.Path]::GetFullPath($EvidenceRoot)
$InstallDir = Join-Path $EvidenceRoot 'installed'
$CompileDir = Join-Path $EvidenceRoot 'setup'
New-Item -ItemType Directory -Path $CompileDir -Force | Out-Null
$Version = (& $Python -c 'from app.build_profile import APP_VERSION; print(APP_VERSION)').Trim()
$Sequence = [int](& $Python -c 'from app.build_profile import RELEASE_SEQUENCE; print(RELEASE_SEQUENCE)')
$VersionParts = (($Version -split '-', 2)[0] -split '\.')
$FileVersion = '{0}.{1}.{2}.{3}' -f (
    [int]$VersionParts[0], [int]$VersionParts[1],
    [int]$VersionParts[2], $Sequence
)
$Installer = Join-Path $CompileDir "RF Next Companion Setup $Version-smoke.exe"

Push-Location $Project
try {
    & $Nsis @(
        '/V2', '/WX', '/DDEV_SMOKE',
        "/DAPP_SOURCE=$SourceDir", "/DAPP_OUTFILE=$Installer",
        "/DAPP_VERSION=$Version", "/DAPP_FILE_VERSION=$FileVersion",
        '.\packaging\agent-installer.nsi'
    )
    if ($LASTEXITCODE) { throw 'Falha ao compilar o instalador de ensaio do Agent.' }
} finally {
    Pop-Location
}
if ([string](Get-AuthenticodeSignature -LiteralPath $Installer).Status -ne 'NotSigned') {
    throw 'O projeto decidiu não usar Authenticode; o ensaio encontrou estado inesperado.'
}

$PreviousCompatLayer = $env:__COMPAT_LAYER
try {
    $env:__COMPAT_LAYER = 'RunAsInvoker'
    New-Item -ItemType Directory -Path (Join-Path $InstallDir '_internal') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $InstallDir 'RF QOL Agent.exe') -Value 'legacy-smoke'
    Set-Content -LiteralPath (Join-Path $InstallDir '_internal\legacy-smoke.txt') -Value 'legacy-smoke'
    $Install = Start-Process -FilePath $Installer -ArgumentList @('/S', "/D=$InstallDir") -PassThru
    if (-not $Install.WaitForExit(120000)) {
        Stop-Process -Id $Install.Id -Force -ErrorAction SilentlyContinue
        throw 'Instalação de ensaio excedeu 120 segundos.'
    }
    if ($Install.ExitCode) { throw "Instalação de ensaio falhou: $($Install.ExitCode)" }
    $Executable = Join-Path $InstallDir 'RF Next Companion.exe'
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw 'Executável do Agent não foi instalado.'
    }
    if (Test-Path -LiteralPath (Join-Path $InstallDir 'RF QOL Agent.exe')) {
        throw 'A atualização deixou o executável legado instalado.'
    }
    if (Test-Path -LiteralPath (Join-Path $InstallDir '_internal\legacy-smoke.txt')) {
        throw 'A atualização deixou arquivos internos da versão anterior.'
    }
    $SelfTest = Start-Process -FilePath $Executable -ArgumentList '--self-test' -PassThru
    if (-not $SelfTest.WaitForExit(60000)) {
        Stop-Process -Id $SelfTest.Id -Force -ErrorAction SilentlyContinue
        throw 'Autoteste instalado excedeu 60 segundos.'
    }
    if ($SelfTest.ExitCode) { throw "Autoteste instalado falhou: $($SelfTest.ExitCode)" }
} finally {
    $Uninstaller = Join-Path $InstallDir 'Uninstall.exe'
    if (Test-Path -LiteralPath $Uninstaller -PathType Leaf) {
        $Uninstall = Start-Process -FilePath $Uninstaller -ArgumentList @('/S', "_?=$InstallDir") -PassThru
        if (-not $Uninstall.WaitForExit(120000)) {
            Stop-Process -Id $Uninstall.Id -Force -ErrorAction SilentlyContinue
            throw 'Desinstalação de ensaio excedeu 120 segundos.'
        }
        if ($Uninstall.ExitCode) { throw "Desinstalação de ensaio falhou: $($Uninstall.ExitCode)" }
    }
    $env:__COMPAT_LAYER = $PreviousCompatLayer
}
if (Test-Path -LiteralPath (Join-Path $InstallDir 'RF Next Companion.exe')) {
    throw 'A desinstalação deixou o executável do Agent.'
}
$Result = [ordered]@{
    status = 'passed'
    tested_at_utc = [DateTime]::UtcNow.ToString('o')
    version = $Version
    installer_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Installer).Hash
    compiler = (& $Nsis '/VERSION' | Out-String).Trim()
    compiler_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Nsis).Hash
    authenticode_status = 'NotSigned'
    packaged_self_test = 'passed'
    legacy_install_migration = 'passed'
    installed_executable_removed = $true
}
$ResultPath = Join-Path $EvidenceRoot 'agent-installer-smoke-result.json'
$Result | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding UTF8
Write-Output $ResultPath
