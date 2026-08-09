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
$Installer = Join-Path $CompileDir 'RF QOL Setup 1.0.0-smoke.exe'
New-Item -ItemType Directory -Path $CompileDir -Force | Out-Null

Push-Location $Project
try {
    & $Nsis '/V2' '/WX' '/DDEV_SMOKE' "/DAPP_OUTFILE=$Installer" '.\packaging\installer.nsi'
    if ($LASTEXITCODE) { throw 'Falha ao compilar instalador de ensaio.' }
} finally {
    Pop-Location
}
$AuthenticodeStatus = [string](Get-AuthenticodeSignature -LiteralPath $Installer).Status
if ($AuthenticodeStatus -ne 'NotSigned') {
    throw "Instalador de ensaio deve permanecer NotSigned: $AuthenticodeStatus"
}

$PreviousSelfTest = $env:RFQOL_SELF_TEST
try {
    $env:RFQOL_SELF_TEST = '1'
    $Install = Start-Process -FilePath $Installer -ArgumentList @('/S', "/D=$InstallDir") -Wait -PassThru
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
        $Uninstall = Start-Process -FilePath $Uninstaller -ArgumentList '/S' -Wait -PassThru
        if ($Uninstall.ExitCode) { Write-Error "Desinstalação de ensaio falhou: $($Uninstall.ExitCode)" }
    }
    $env:RFQOL_SELF_TEST = $PreviousSelfTest
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
