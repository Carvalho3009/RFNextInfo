$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
$LocalPython = 'C:\Users\celc3\AppData\Local\Programs\Python\Python313\python.exe'
$Python = if ($env:RFNEXT_BUILD_PYTHON) {
    $env:RFNEXT_BUILD_PYTHON
} elseif (Test-Path -LiteralPath $LocalPython) {
    $LocalPython
} else {
    'python'
}
$Dependencies = Join-Path $Project '.deps313'
if (Test-Path -LiteralPath $Dependencies) { $env:PYTHONPATH = $Dependencies }

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
        if (-not $Nsis) {
            $LocalNsis = Join-Path $Project '.toolchain\nsis-3.12\nsis-3.12\makensis.exe'
            if (Test-Path -LiteralPath $LocalNsis) { $Nsis = Get-Item -LiteralPath $LocalNsis }
        }
        if ($Nsis) {
            & $Nsis.FullName '.\packaging\installer.nsi'
            if ($LASTEXITCODE) { throw 'Falha ao gerar o instalador.' }
        } else {
            Write-Warning 'Inno Setup/NSIS não encontrado; executável portátil gerado em dist.'
        }
    }
} finally {
    Pop-Location
}
