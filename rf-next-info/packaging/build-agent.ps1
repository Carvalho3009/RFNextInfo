param([switch]$SkipTests)

$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Project '.venv313\Scripts\python.exe'
$Python = if ($env:RFQOL_BUILD_PYTHON) {
    $env:RFQOL_BUILD_PYTHON
} elseif (Test-Path -LiteralPath $VenvPython) {
    $VenvPython
} else {
    'python'
}

Push-Location $Project
try {
    & $Python -c 'import PySide6, PyInstaller'
    if ($LASTEXITCODE) {
        throw 'PySide6 ou PyInstaller não está disponível no ambiente de build.'
    }
    if (-not $SkipTests) {
        & $Python -m unittest discover -s tests -p 'test_*.py'
        if ($LASTEXITCODE) { throw 'A regressão falhou; build do Agent cancelado.' }
    }

    & $Python -m PyInstaller --clean --noconfirm '.\packaging\RFQOLAgent.spec'
    if ($LASTEXITCODE) { throw 'Falha ao gerar o executável separado do Agent.' }

    $Executable = Join-Path $Project 'dist\RF Next Companion\RF Next Companion.exe'
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw 'O executável do Agent não foi encontrado após o build.'
    }
    $PreviousCompatLayer = $env:__COMPAT_LAYER
    try {
        $env:__COMPAT_LAYER = 'RunAsInvoker'
        $SelfTest = Start-Process -FilePath $Executable -ArgumentList '--self-test' -PassThru
        if (-not $SelfTest.WaitForExit(60000)) {
            Stop-Process -Id $SelfTest.Id -Force -ErrorAction SilentlyContinue
            throw 'O autoteste do Agent empacotado excedeu 60 segundos.'
        }
        if ($SelfTest.ExitCode) {
            throw "O autoteste do Agent empacotado falhou (código $($SelfTest.ExitCode))."
        }
    } finally {
        $env:__COMPAT_LAYER = $PreviousCompatLayer
    }

    Write-Output $Executable
} finally {
    Pop-Location
}
