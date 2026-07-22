[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$AesKey
)

$ErrorActionPreference = 'Stop'
$repak = 'K:\MCP\projects\rf-next\tools\repak-v0.2.3\repak.exe'
$pakDir = 'K:\MCP\projects\rf-next\analysis\1.28.5\oodle-assets\pakcache-full'
$outputDir = 'K:\MCP\projects\rf-next\analysis\1.28.5\auction-live'
$result = Join-Path $outputDir 'auction-assets.csv'
$progress = Join-Path $outputDir 'auction-assets-progress.log'

New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
"Pak,Entry" | Set-Content -LiteralPath $result -Encoding utf8
$paks = Get-ChildItem -LiteralPath $pakDir -Filter '*.pak' -File | Sort-Object Name

for ($index = 0; $index -lt $paks.Count; $index++) {
    $pak = $paks[$index]
    $entries = & $repak --aes-key $AesKey list $pak.FullName 2>$null
    foreach ($entry in $entries) {
        if ($entry -match '(?i)(exchange|auction)') {
            '"{0}","{1}"' -f $pak.Name, ($entry -replace '"', '""') |
                Add-Content -LiteralPath $result -Encoding utf8
        }
    }
    '{0:u} {1}/{2} {3}' -f (Get-Date), ($index + 1), $paks.Count, $pak.Name |
        Add-Content -LiteralPath $progress -Encoding utf8
}

$count = [Math]::Max(0, (Get-Content -LiteralPath $result).Count - 1)
Write-Host "Concluído: $($paks.Count) paks; $count entradas; $result"
