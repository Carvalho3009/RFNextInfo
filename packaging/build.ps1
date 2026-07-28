$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
$Python = if ($env:RFNEXT_BUILD_PYTHON) { $env:RFNEXT_BUILD_PYTHON } else { 'python' }

Push-Location $Project
try {
    & $Python -m PyInstaller --clean --noconfirm '.\packaging\RFNextInfo.spec'
    if ($LASTEXITCODE) { throw 'Falha ao gerar o executável.' }
    $Inno = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($Inno) {
        & $Inno.Source '.\packaging\installer.iss'
        if ($LASTEXITCODE) { throw 'Falha ao gerar o instalador.' }
    } else {
        $Nsis = Get-Command makensis.exe -ErrorAction SilentlyContinue
        if ($Nsis) {
            & $Nsis.Source '.\packaging\installer.nsi'
            if ($LASTEXITCODE) { throw 'Falha ao gerar o instalador.' }
        } else {
            Write-Warning 'Inno Setup/NSIS não encontrado; executável portátil gerado em dist.'
        }
    }
} finally {
    Pop-Location
}
