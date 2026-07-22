[CmdletBinding()]
param(
    [ValidateRange(8, 500)]
    [int]$MaxFunctions = 120
)

$ErrorActionPreference = 'Stop'

$ghidraHome = 'K:\MCP\tools\ghidra_12.1.2_PUBLIC'
$headless = Join-Path $ghidraHome 'support\analyzeHeadless.bat'
$projectDir = 'K:\MCP\projects\rf-next\Ghidra'
$projectName = 'RF BOT'
$programName = 'libUnreal.so'
$scriptDir = Split-Path -Parent $PSCommandPath
$outputDir = 'K:\MCP\projects\rf-next\analysis\1.28.5\oodle-auto'
$reportPath = Join-Path $outputDir 'RFNext-Oodle-config-xrefs.md'
$logPath = Join-Path $outputDir 'config-xrefs-headless.log'
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
    -process $programName `
    -noanalysis `
    -scriptPath $scriptDir `
    -postScript RFNextOodleConfigAnalyzer.java $reportPath $MaxFunctions `
    2>&1 | Tee-Object -FilePath $logPath

if ($LASTEXITCODE -ne 0) {
    throw "Ghidra terminou com código $LASTEXITCODE. Consulte: $logPath"
}

Write-Host "Concluído: $reportPath"
