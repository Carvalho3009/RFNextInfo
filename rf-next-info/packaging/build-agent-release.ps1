param(
    [switch]$SkipTests,
    [string]$DistRoot = '',
    [string]$BuildRoot = '',
    [string]$OutputRoot = '',
    [string]$Nsis = $env:RFQOL_NSIS
)

$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
$Python = if ($env:RFQOL_BUILD_PYTHON) {
    $env:RFQOL_BUILD_PYTHON
} else {
    Join-Path $Project '.venv313\Scripts\python.exe'
}
if (-not $Nsis) { $Nsis = 'K:\MCP\_tools\nsis-3.12\portable\makensis.exe' }
if (-not (Test-Path -LiteralPath $Nsis -PathType Leaf)) { throw 'NSIS não encontrado.' }
$Version = (& $Python -c 'from app.build_profile import APP_VERSION; print(APP_VERSION)').Trim()
$Sequence = [int](& $Python -c 'from app.build_profile import RELEASE_SEQUENCE; print(RELEASE_SEQUENCE)')
if (-not $DistRoot) { $DistRoot = Join-Path $Project "dist-agent-$Version" }
if (-not $BuildRoot) { $BuildRoot = Join-Path $Project "build-agent-$Version" }
if (-not $OutputRoot) { $OutputRoot = Join-Path $Project "release-agent-$Version" }
$DistRoot = [IO.Path]::GetFullPath($DistRoot)
$BuildRoot = [IO.Path]::GetFullPath($BuildRoot)
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$PackageDir = Join-Path $DistRoot 'RF Next Companion'
$VersionParts = (($Version -split '-', 2)[0] -split '\.')
$FileVersion = '{0}.{1}.{2}.{3}' -f (
    [int]$VersionParts[0], [int]$VersionParts[1],
    [int]$VersionParts[2], $Sequence
)
$Installer = Join-Path $OutputRoot "RF-Next-Companion-Setup-$Version.exe"

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
Push-Location $Project
try {
    & $Python -c 'from app.build_profile import validate_build_profile; validate_build_profile(release=True)'
    if ($LASTEXITCODE) { throw 'Perfil do Agent inválido.' }
    if (-not $SkipTests) {
        & $Python -m unittest discover -s tests -p 'test_*.py'
        if ($LASTEXITCODE) { throw 'Regressão falhou; release cancelada.' }
    }
    & $Python -m PyInstaller --clean --noconfirm --distpath $DistRoot --workpath $BuildRoot '.\packaging\RFQOLAgent.spec'
    if ($LASTEXITCODE) { throw 'Falha ao empacotar o Agent.' }
    $Executable = Join-Path $PackageDir 'RF Next Companion.exe'
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { throw 'Executável não encontrado.' }
    $PreviousCompatLayer = $env:__COMPAT_LAYER
    try {
        $env:__COMPAT_LAYER = 'RunAsInvoker'
        $SelfTest = Start-Process -FilePath $Executable -ArgumentList '--self-test' -WindowStyle Hidden -PassThru
        if (-not $SelfTest.WaitForExit(60000)) {
            Stop-Process -Id $SelfTest.Id -Force -ErrorAction SilentlyContinue
            throw 'Autoteste empacotado excedeu 60 segundos.'
        }
        if ($SelfTest.ExitCode) { throw "Autoteste empacotado falhou: $($SelfTest.ExitCode)" }
    } finally {
        $env:__COMPAT_LAYER = $PreviousCompatLayer
    }
    & $Nsis @(
        '/V2', '/WX', "/DAPP_SOURCE=$PackageDir", "/DAPP_OUTFILE=$Installer",
        "/DAPP_VERSION=$Version", "/DAPP_FILE_VERSION=$FileVersion",
        '.\packaging\agent-installer.nsi'
    )
    if ($LASTEXITCODE) { throw 'Falha ao compilar o instalador público do Agent.' }
    $Signature = [string](Get-AuthenticodeSignature -LiteralPath $Installer).Status
    if ($Signature -ne 'NotSigned') { throw "Estado Authenticode inesperado: $Signature" }
    $SmokeEvidence = & '.\packaging\test-agent-installer.ps1' -SourceDir $PackageDir -Nsis $Nsis
    if ($LASTEXITCODE) { throw 'Ensaio automático do instalador falhou.' }
    [ordered]@{
        version = $Version
        release_sequence = $Sequence
        installer = $Installer
        installer_size = (Get-Item -LiteralPath $Installer).Length
        installer_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Installer).Hash
        authenticode_status = $Signature
        packaged_self_test = 'passed'
        installer_smoke_evidence = ($SmokeEvidence | Select-Object -Last 1)
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputRoot 'build-evidence.json') -Encoding UTF8
    Write-Output $Installer
} finally {
    Pop-Location
}
