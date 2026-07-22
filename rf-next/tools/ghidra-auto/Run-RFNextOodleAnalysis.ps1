[CmdletBinding()]
param(
    [ValidateRange(0, 8)]
    [int]$Depth = 4,

    [ValidateRange(8, 1000)]
    [int]$MaxFunctions = 250
)

$ErrorActionPreference = 'Stop'

$ghidraHome = 'K:\MCP\tools\ghidra_12.1.2_PUBLIC'
$headless = Join-Path $ghidraHome 'support\analyzeHeadless.bat'
$projectDir = 'K:\MCP\projects\rf-next\Ghidra'
$projectName = 'RF BOT'
$programName = 'libUnreal.so'
$scriptDir = Split-Path -Parent $PSCommandPath
$outputDir = 'K:\MCP\projects\rf-next\analysis\1.28.5\oodle-auto'
$reportPath = Join-Path $outputDir 'RFNext-Oodle-report.md'
$logPath = Join-Path $outputDir 'headless.log'
$lockPath = Join-Path $projectDir "$projectName.lock"

if (-not (Test-Path -LiteralPath $headless)) {
    throw "Ghidra headless não encontrado: $headless"
}
if (Test-Path -LiteralPath $lockPath) {
    throw 'Salve e feche o Ghidra antes de iniciar. O projeto RF BOT ainda está aberto.'
}

New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

# Keeps Windows awake only while this process is running; no power-plan change.
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
public static class RFNextAwake {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint flags);
}
'@

$ES_CONTINUOUS = [uint32]2147483648
$ES_SYSTEM_REQUIRED = [uint32]0x00000001
[void][RFNextAwake]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)

try {
    Write-Host "Relatório: $reportPath"
    Write-Host "Profundidade: $Depth | limite: $MaxFunctions"

    & $headless `
        $projectDir `
        $projectName `
        -process $programName `
        -noanalysis `
        -scriptPath $scriptDir `
        -postScript RFNextOodleAnalyzer.java $reportPath $Depth $MaxFunctions `
        2>&1 | Tee-Object -FilePath $logPath

    if ($LASTEXITCODE -ne 0) {
        throw "Ghidra terminou com código $LASTEXITCODE. Consulte: $logPath"
    }
}
finally {
    [void][RFNextAwake]::SetThreadExecutionState($ES_CONTINUOUS)
}

Write-Host "Concluído: $reportPath"
