param(
    [string]$Nsis = $env:RFQOL_NSIS,
    [string]$EvidenceRoot = ''
)

$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
if (-not $Nsis) {
    $Command = Get-Command makensis.exe -ErrorAction SilentlyContinue
    if ($Command) { $Nsis = $Command.Source }
}
if (-not $Nsis -or -not (Test-Path -LiteralPath $Nsis -PathType Leaf)) {
    throw 'Informe makensis.exe por -Nsis ou RFQOL_NSIS.'
}
if (-not (Test-Path -LiteralPath (Join-Path $Project 'dist\RF QOL\RF QOL.exe'))) {
    throw 'Gere o pacote portátil antes do ensaio do instalador.'
}
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path ([IO.Path]::GetTempPath()) (
        'rf-qol-installer-smoke-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    )
}
$EvidenceRoot = [IO.Path]::GetFullPath($EvidenceRoot)
$InstallDir = Join-Path $EvidenceRoot 'installed'
$CompileDir = Join-Path $EvidenceRoot 'setup'
$Python = if ($env:RFQOL_BUILD_PYTHON) {
    $env:RFQOL_BUILD_PYTHON
} else {
    Join-Path $Project '.venv313\Scripts\python.exe'
}
$Version = (& $Python -c 'from app.main import VERSION; print(VERSION)').Trim()
$Sequence = [int](& $Python -c 'from app.main import RELEASE_SEQUENCE; print(RELEASE_SEQUENCE)')
$VersionParts = (($Version -split '-', 2)[0] -split '\.')
$FileVersion = '{0}.{1}.{2}.{3}' -f (
    [int]$VersionParts[0], [int]$VersionParts[1],
    [int]$VersionParts[2], $Sequence
)
$BuildProfile = (& $Python -c 'from app.build_profile import PROFILE_NAME; print(PROFILE_NAME)').Trim()
$Installer = Join-Path $CompileDir "RF QOL Setup $Version-smoke.exe"
New-Item -ItemType Directory -Path $CompileDir -Force | Out-Null

Push-Location $Project
try {
    $NsisArguments = @(
        '/V2', '/WX', '/DDEV_SMOKE', "/DAPP_OUTFILE=$Installer",
        "/DAPP_VERSION=$Version", "/DAPP_FILE_VERSION=$FileVersion"
    )
    if ($BuildProfile -eq 'staging') { $NsisArguments += '/DSTAGING_PROFILE' }
    if ($BuildProfile -eq 'beta') { $NsisArguments += '/DBETA_PROFILE' }
    $NsisArguments += '.\packaging\installer.nsi'
    & $Nsis @NsisArguments
    if ($LASTEXITCODE) { throw 'Falha ao compilar instalador de ensaio.' }
} finally {
    Pop-Location
}
$AuthenticodeStatus = [string](Get-AuthenticodeSignature -LiteralPath $Installer).Status
if ($AuthenticodeStatus -ne 'NotSigned') {
    throw "Instalador de ensaio deve permanecer NotSigned: $AuthenticodeStatus"
}

$PreviousSelfTest = $env:RFQOL_SELF_TEST
$PreviousCompatLayer = $env:__COMPAT_LAYER
try {
    $env:RFQOL_SELF_TEST = '1'
    $env:__COMPAT_LAYER = 'RunAsInvoker'
    $Install = Start-Process -FilePath $Installer -ArgumentList @('/S', "/D=$InstallDir") -PassThru
    if (-not $Install.WaitForExit(90000)) {
        Stop-Process -Id $Install.Id -Force -ErrorAction SilentlyContinue
        throw 'Instalação de ensaio excedeu 90 segundos.'
    }
    if ($Install.ExitCode) { throw "Instalação de ensaio falhou: $($Install.ExitCode)" }
    $Executable = Join-Path $InstallDir 'RF QOL.exe'
    $InstallTestLog = Join-Path $InstallDir 'logs\install.log'
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw 'Executável não foi instalado.'
    }
    if (-not (Test-Path -LiteralPath $InstallTestLog -PathType Leaf) -or
        (Get-Content -LiteralPath $InstallTestLog -Raw) -notmatch 'self_test=0') {
        throw 'Autoteste pós-instalação não foi comprovado.'
    }
} finally {
    $Uninstaller = Join-Path $InstallDir 'Uninstall.exe'
    if (Test-Path -LiteralPath $Uninstaller -PathType Leaf) {
        $Uninstall = Start-Process -FilePath $Uninstaller -ArgumentList @(
            '/S', "_?=$InstallDir"
        ) -PassThru
        if (-not $Uninstall.WaitForExit(120000)) {
            Stop-Process -Id $Uninstall.Id -Force -ErrorAction SilentlyContinue
            throw 'Desinstalação de ensaio excedeu 120 segundos.'
        }
        if ($Uninstall.ExitCode) { Write-Error "Desinstalação de ensaio falhou: $($Uninstall.ExitCode)" }
    }
    $env:RFQOL_SELF_TEST = $PreviousSelfTest
    $env:__COMPAT_LAYER = $PreviousCompatLayer
}
if (Test-Path -LiteralPath (Join-Path $InstallDir 'RF QOL.exe')) {
    throw 'Desinstalação deixou o executável no destino.'
}
$Result = [ordered]@{
    status = 'passed'
    tested_at_utc = [DateTime]::UtcNow.ToString('o')
    installer_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Installer).Hash
    compiler = (& $Nsis '/VERSION' | Out-String).Trim()
    compiler_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Nsis).Hash
    authenticode_status = $AuthenticodeStatus
    installed_executable_removed = $true
}
$ResultPath = Join-Path $EvidenceRoot 'installer-smoke-result.json'
$Result | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding UTF8
Write-Output $ResultPath
