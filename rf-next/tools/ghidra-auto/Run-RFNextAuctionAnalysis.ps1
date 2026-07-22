[CmdletBinding()]
param(
    [ValidateRange(8, 300)]
    [int]$MaxFunctions = 100
)

$ErrorActionPreference = 'Stop'

$ghidraHome = 'K:\MCP\tools\ghidra_12.1.2_PUBLIC'
$headless = Join-Path $ghidraHome 'support\analyzeHeadless.bat'
$projectDir = 'K:\MCP\projects\rf-next\Ghidra'
$projectName = 'RF BOT'
$scriptDir = Split-Path -Parent $PSCommandPath
$outputDir = 'K:\MCP\projects\rf-next\analysis\1.28.5\auction-live'
$reportPath = Join-Path $outputDir 'RFNext-Auction-handlers.md'
$logPath = Join-Path $outputDir 'auction-headless.log'
$targetsPath = Join-Path $scriptDir 'auction-targets.txt'
$lockPath = Join-Path $projectDir "$projectName.lock"

if (-not (Test-Path -LiteralPath $headless)) {
    throw "Ghidra headless não encontrado: $headless"
}
if (Test-Path -LiteralPath $lockPath) {
    throw 'Salve e feche o Ghidra antes de iniciar. O projeto RF BOT ainda está aberto.'
}

New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

& $headless `
    $projectDir `
    $projectName `
    -process libUnreal.so `
    -noanalysis `
    -scriptPath $scriptDir `
    -postScript RFNextOodleConfigAnalyzer.java $reportPath $MaxFunctions $targetsPath `
    2>&1 | Tee-Object -FilePath $logPath

if ($LASTEXITCODE -ne 0) {
    throw "Ghidra terminou com código $LASTEXITCODE. Consulte: $logPath"
}

Write-Host "Concluído: $reportPath"
