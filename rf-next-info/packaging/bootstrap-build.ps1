param(
    [string]$BasePython = 'C:\Users\celc3\AppData\Local\Programs\Python\Python313\python.exe',
    [string]$Wheelhouse = ''
)

$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
$Environment = Join-Path $Project '.venv313'
$Python = Join-Path $Environment 'Scripts\python.exe'
$Lock = Join-Path $Project 'requirements-lock-win-x64-py313.txt'

if (-not (Test-Path -LiteralPath $BasePython -PathType Leaf)) {
    throw "Python base não encontrado: $BasePython"
}

& $BasePython -m venv --clear $Environment
if ($LASTEXITCODE) { throw 'Não foi possível criar o ambiente virtual.' }

$Arguments = @('-m', 'pip', 'install', '--require-hashes', '-r', $Lock)
if ($Wheelhouse) {
    $ResolvedWheelhouse = (Resolve-Path -LiteralPath $Wheelhouse).Path
    $Arguments += @('--no-index', '--find-links', $ResolvedWheelhouse)
}
& $Python @Arguments
if ($LASTEXITCODE) { throw 'Não foi possível instalar o lock de build.' }

& $Python -m pip check
if ($LASTEXITCODE) { throw 'O ambiente virtual contém conflitos.' }
Write-Output $Python
