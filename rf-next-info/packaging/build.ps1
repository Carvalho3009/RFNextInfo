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
if (-not $env:RFNEXT_BUILD_PYTHON -and (Test-Path -LiteralPath $Dependencies)) {
    $env:PYTHONPATH = $Dependencies
}

Push-Location $Project
try {
    & $Python -c 'import PySide6'
    if ($LASTEXITCODE) {
        throw 'PySide6 não está disponível no ambiente de build. Instale requirements.txt antes de empacotar.'
    }
    & $Python -m PyInstaller --clean --noconfirm '.\packaging\RFNextInfo.spec'
    if ($LASTEXITCODE) { throw 'Falha ao gerar o executável.' }
    $PreviousCompatLayer = $env:__COMPAT_LAYER
    try {
        $env:__COMPAT_LAYER = 'RunAsInvoker'
        $SelfTest = Start-Process `
            -FilePath '.\dist\RFNextInfo\RFNextInfo.exe' `
            -ArgumentList '--self-test' `
            -PassThru
        if (-not $SelfTest.WaitForExit(60000)) {
            Stop-Process -Id $SelfTest.Id -Force -ErrorAction SilentlyContinue
            throw 'O autoteste do executável empacotado excedeu 60 segundos.'
        }
        if ($SelfTest.ExitCode) {
            throw "O autoteste do executável empacotado falhou (código $($SelfTest.ExitCode))."
        }
        # O autoteste valida escrita install-local. O estado criado por ele é
        # descartável e não deve ser distribuído como dado de outro computador.
        foreach ($RuntimeDirectory in @('data', 'database', 'logs', 'cache', 'updates', 'Capturas')) {
            $Generated = Join-Path $Project "dist\RFNextInfo\$RuntimeDirectory"
            if (Test-Path -LiteralPath $Generated) {
                Remove-Item -LiteralPath $Generated -Recurse -Force
            }
        }
    } finally {
        $env:__COMPAT_LAYER = $PreviousCompatLayer
    }
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
            & $Nsis.Source '.\packaging\installer.nsi'
            if ($LASTEXITCODE) { throw 'Falha ao gerar o instalador.' }
        } else {
            Write-Warning 'Inno Setup/NSIS não encontrado; executável portátil gerado em dist.'
        }
    }
} finally {
    Pop-Location
}
