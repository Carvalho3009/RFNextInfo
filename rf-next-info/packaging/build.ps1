param([switch]$Release, [switch]$SkipTests)

$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
$LocalPython = 'C:\Users\celc3\AppData\Local\Programs\Python\Python313\python.exe'
$VenvPython = Join-Path $Project '.venv313\Scripts\python.exe'
$Python = if ($env:RFQOL_BUILD_PYTHON) {
    $env:RFQOL_BUILD_PYTHON
} elseif (Test-Path -LiteralPath $VenvPython) {
    $VenvPython
} elseif (Test-Path -LiteralPath $LocalPython) {
    $LocalPython
} else {
    'python'
}

Push-Location $Project
try {
    $Dirty = [bool](git status --porcelain)
    if ($Release -and $Dirty) {
        throw 'Build de release exige commit limpo.'
    }
    foreach ($Generated in @(
        '.\dist\update-manifest.json',
        '.\dist\release-provenance-signature.json'
    )) {
        if (Test-Path -LiteralPath $Generated -PathType Leaf) {
            Remove-Item -LiteralPath $Generated -Force
        }
    }
    & $Python -c 'import PySide6'
    if ($LASTEXITCODE) {
        throw 'PySide6 não está disponível no ambiente de build.'
    }
    if (-not $SkipTests) {
        & $Python -m unittest discover -s tests -p 'test_*.py'
        if ($LASTEXITCODE) { throw 'A regressão falhou; build cancelado.' }
    }
    if ($Release) {
        & $Python -c 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)'
        if ($LASTEXITCODE) { throw 'Build de release exige ambiente virtual isolado.' }
        & $Python -c 'from app.license import validate_release_configuration as a; from app.updater import validate_release_configuration as b; a(); b()'
        if ($LASTEXITCODE) { throw 'Configuração de confiança de produção incompleta.' }
    }
    & $Python -m PyInstaller --clean --noconfirm '.\packaging\RFNextInfo.spec'
    if ($LASTEXITCODE) { throw 'Falha ao gerar o executável.' }

    $Dist = Join-Path $Project 'dist\RF QOL'
    $Executable = Join-Path $Dist 'RF QOL.exe'
    $PreviousCompatLayer = $env:__COMPAT_LAYER
    $PreviousSelfTest = $env:RFQOL_SELF_TEST
    try {
        $env:__COMPAT_LAYER = 'RunAsInvoker'
        $env:RFQOL_SELF_TEST = '1'
        $SelfTest = Start-Process -FilePath $Executable -ArgumentList '--self-test' -PassThru
        if (-not $SelfTest.WaitForExit(60000)) {
            Stop-Process -Id $SelfTest.Id -Force -ErrorAction SilentlyContinue
            throw 'O autoteste do executável empacotado excedeu 60 segundos.'
        }
        if ($SelfTest.ExitCode) {
            throw "O autoteste do executável empacotado falhou (código $($SelfTest.ExitCode))."
        }
        foreach ($RuntimeDirectory in @('data', 'machine-data', 'database', 'logs', 'cache', 'updates', 'Capturas')) {
            $Generated = Join-Path $Dist $RuntimeDirectory
            if (Test-Path -LiteralPath $Generated) {
                Remove-Item -LiteralPath $Generated -Recurse -Force
            }
        }
    } finally {
        $env:__COMPAT_LAYER = $PreviousCompatLayer
        $env:RFQOL_SELF_TEST = $PreviousSelfTest
    }

    & $Python -m pip check
    if ($LASTEXITCODE) { throw 'Ambiente de dependências inconsistente.' }
    & $Python -m pip list --local --format=json | Set-Content -LiteralPath (Join-Path $Dist 'sbom-python.json') -Encoding UTF8
    Copy-Item -LiteralPath '.\requirements-lock-win-x64-py313.txt' -Destination $Dist -Force

    $NsisPath = if ($env:RFQOL_NSIS) {
        if (-not (Test-Path -LiteralPath $env:RFQOL_NSIS -PathType Leaf)) {
            throw "RFQOL_NSIS não aponta para makensis.exe: $($env:RFQOL_NSIS)"
        }
        (Resolve-Path -LiteralPath $env:RFQOL_NSIS).Path
    } else {
        $Command = Get-Command makensis.exe -ErrorAction SilentlyContinue
        if ($Command) { $Command.Source } else { $null }
    }
    $Installer = $null
    if (-not $NsisPath) {
        if ($Release) { throw 'NSIS é obrigatório para o instalador de release.' }
        Write-Warning 'NSIS não encontrado; somente o pacote portátil foi gerado.'
    } else {
        & $NsisPath '/V2' '/WX' '.\packaging\installer.nsi'
        if ($LASTEXITCODE) { throw 'Falha ao gerar o instalador.' }
        $Installer = Join-Path $Project 'dist\RF QOL Setup 1.0.0.exe'
    }

    if ($Release) {
        foreach ($name in 'RFQOL_UPDATE_PRIVATE_KEY', 'RFQOL_UPDATE_KEY_ID') {
            if (-not (Get-Item -LiteralPath "env:$name" -ErrorAction SilentlyContinue).Value) {
                throw "$name é obrigatório para assinar o manifesto."
            }
        }
        & $Python '.\tools\sign_update_manifest.py' `
            --installer $Installer --version '1.0.0' --sequence 1 `
            --key-id $env:RFQOL_UPDATE_KEY_ID `
            --private-key $env:RFQOL_UPDATE_PRIVATE_KEY `
            --out '.\dist\update-manifest.json'
        if ($LASTEXITCODE) { throw 'Falha ao assinar o manifesto v2.' }
    }

    $Provenance = [ordered]@{
        product = 'rf-qol'
        version = '1.0.0'
        commit = (git rev-parse HEAD)
        dirty = $Dirty
        python = (& $Python --version 2>&1 | Out-String).Trim()
        executable_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Executable).Hash
        installer_sha256 = if ($Installer) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Installer).Hash } else { $null }
        lock_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath '.\requirements-lock-win-x64-py313.txt').Hash
        sbom_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Dist 'sbom-python.json')).Hash
        manifest_sha256 = if (Test-Path -LiteralPath '.\dist\update-manifest.json') {
            (Get-FileHash -Algorithm SHA256 -LiteralPath '.\dist\update-manifest.json').Hash
        } else { $null }
        pyinstaller = (& $Python -m PyInstaller --version 2>&1 | Out-String).Trim()
        nsis = if ($NsisPath) { (& $NsisPath '/VERSION' | Out-String).Trim() } else { $null }
        nsis_sha256 = if ($NsisPath) { (Get-FileHash -Algorithm SHA256 -LiteralPath $NsisPath).Hash } else { $null }
        authenticode = $false
        release = [bool]$Release
    }
    $Provenance | ConvertTo-Json | Set-Content -LiteralPath '.\dist\release-provenance.json' -Encoding UTF8
    if ($Release) {
        & $Python '.\tools\sign_provenance.py' `
            --provenance '.\dist\release-provenance.json' `
            --key-id $env:RFQOL_UPDATE_KEY_ID `
            --private-key $env:RFQOL_UPDATE_PRIVATE_KEY `
            --out '.\dist\release-provenance-signature.json'
        if ($LASTEXITCODE) { throw 'Falha ao assinar a procedência local.' }
    }
} finally {
    Pop-Location
}
