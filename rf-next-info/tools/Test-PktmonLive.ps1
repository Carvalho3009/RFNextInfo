param(
    [ValidateRange(30, 300)]
    [int]$CaptureSeconds = 90,

    [ValidateRange(5, 60)]
    [int]$RestartSeconds = 15,

    [ValidateRange(1, 128)]
    [int]$SegmentMB = 16,

    [int[]]$Ports = @(12000, 12010, 12020, 12040),

    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version 2

function Convert-ToSearchText {
    param([string]$Text)

    $normalized = $Text.Normalize(
        [Text.NormalizationForm]::FormD
    )
    return (
        ($normalized -replace "\p{Mn}", "") -replace "\s+", " "
    ).ToLowerInvariant()
}

function Invoke-Pktmon {
    param([string[]]$Arguments)

    $output = & pktmon @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw (($output | Out-String).Trim())
    }
    return @($output)
}

function Test-PktmonRunning {
    $output = Invoke-Pktmon @("status")
    $text = Convert-ToSearchText ($output | Out-String)
    if ($text -match "not running|nao esta em execucao") {
        return $false
    }
    return $text -match "running|em execucao"
}

function Start-ProbeCapture {
    param([string]$Path)

    Invoke-Pktmon @(
        "start",
        "--capture",
        "--comp", "nics",
        "--pkt-size", "0",
        "--file-name", $Path,
        "--file-size", "$SegmentMB",
        "--log-mode", "multi-file"
    ) | Out-Null
}

function Wait-Probe {
    param(
        [int]$Seconds,
        [string]$Message
    )

    Write-Host $Message
    for ($remaining = $Seconds; $remaining -gt 0; $remaining -= 10) {
        Write-Host ("  faltam {0} s" -f $remaining)
        Start-Sleep -Seconds ([Math]::Min(10, $remaining))
    }
}

function Convert-Etl {
    param(
        [System.IO.FileInfo]$File,
        [string]$TargetDirectory,
        [string]$Suffix = ""
    )

    $target = Join-Path $TargetDirectory (
        $File.BaseName + $Suffix + ".pcapng"
    )
    try {
        Invoke-Pktmon @("etl2pcap", $File.FullName, "--out", $target) |
            Out-Null
        return [ordered]@{
            file = $File.Name
            bytes = $File.Length
            converted = $true
            output = $target
            error = $null
        }
    } catch {
        return [ordered]@{
            file = $File.Name
            bytes = $File.Length
            converted = $false
            output = $null
            error = $_.Exception.Message
        }
    }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$admin = $principal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $admin) {
    throw "Execute este teste em um PowerShell como Administrador."
}

if (Test-PktmonRunning) {
    throw "Ja existe uma captura PktMon ativa. Encerre-a antes do teste."
}

$filters = Invoke-Pktmon @("filter", "list")
$filterText = Convert-ToSearchText ($filters | Out-String)
$noFilters = $filterText -match (
    "no packet filters|no filters|nenhum filtro|nao ha filtros|\bnenhum\b"
)
if ($filterText -and -not $noFilters) {
    throw (
        "Existem filtros PktMon anteriores. O teste nao vai remove-los. " +
        "Remova-os manualmente apenas se souber que nao estao em uso."
    )
}

if (-not $OutputDirectory) {
    $documents = [Environment]::GetFolderPath("MyDocuments")
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDirectory = Join-Path $documents (
        "Capturas\Diagnosticos\pktmon-live-$stamp"
    )
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$firstPrefix = Join-Path $OutputDirectory "probe-a.etl"
$secondPrefix = Join-Path $OutputDirectory "probe-b.etl"
$resultPath = Join-Path $OutputDirectory "resultado.json"
$started = $false
$createdFilters = $false

$result = [ordered]@{
    schema = "karvalho.rfnext-info.pktmon-probe/v1"
    started_at = (Get-Date).ToString("o")
    capture_seconds = $CaptureSeconds
    restart_seconds = $RestartSeconds
    segment_mb = $SegmentMB
    ports = @($Ports)
    active_closed_segments = @()
    active_current_segment = $null
    final_segments = @()
    stop_ms = $null
    start_ms = $null
    capture_gap_ms = $null
    error = $null
}

try {
    $index = 0
    foreach ($port in ($Ports | Select-Object -Unique)) {
        if ($port -lt 1 -or $port -gt 65535) {
            throw "Porta invalida: $port"
        }
        $index++
        Invoke-Pktmon @(
            "filter", "add", "RFNextProbe$index",
            "-t", "TCP",
            "-p", "$port"
        ) | Out-Null
        $createdFilters = $true
    }

    Start-ProbeCapture $firstPrefix
    $started = $true
    Wait-Probe $CaptureSeconds (
        "Jogue normalmente para gerar trafego nas portas do RF NEXT."
    )

    $activeFiles = @(
        Get-ChildItem -LiteralPath $OutputDirectory -Filter "probe-a*.etl" |
            Sort-Object LastWriteTimeUtc, Name
    )
    if ($activeFiles.Count -gt 1) {
        foreach ($file in $activeFiles[0..($activeFiles.Count - 2)]) {
            $result.active_closed_segments += Convert-Etl (
                $file
            ) $OutputDirectory ".closed-active"
        }
    }
    if ($activeFiles.Count -gt 0) {
        $result.active_current_segment = Convert-Etl (
            $activeFiles[-1]
        ) $OutputDirectory ".active"
    }

    $gapTimer = [Diagnostics.Stopwatch]::StartNew()
    $timer = [Diagnostics.Stopwatch]::StartNew()
    Invoke-Pktmon @("stop") | Out-Null
    $timer.Stop()
    $result.stop_ms = [Math]::Round($timer.Elapsed.TotalMilliseconds, 2)
    $started = $false

    $restartFilters = Convert-ToSearchText (
        (Invoke-Pktmon @("filter", "list")) | Out-String
    )
    if ($restartFilters -notmatch "rfnextprobe") {
        $index = 0
        foreach ($port in ($Ports | Select-Object -Unique)) {
            $index++
            Invoke-Pktmon @(
                "filter", "add", "RFNextProbe$index",
                "-t", "TCP",
                "-p", "$port"
            ) | Out-Null
        }
    }

    $timer.Restart()
    Start-ProbeCapture $secondPrefix
    $timer.Stop()
    $gapTimer.Stop()
    $result.start_ms = [Math]::Round($timer.Elapsed.TotalMilliseconds, 2)
    $result.capture_gap_ms = [Math]::Round(
        $gapTimer.Elapsed.TotalMilliseconds, 2
    )
    $started = $true

    Wait-Probe $RestartSeconds "Validando a captura depois do reinicio."
    Invoke-Pktmon @("stop") | Out-Null
    $started = $false

    $allFiles = @(
        Get-ChildItem -LiteralPath $OutputDirectory -Filter "probe-*.etl" |
            Sort-Object LastWriteTimeUtc, Name
    )
    foreach ($file in $allFiles) {
        $result.final_segments += Convert-Etl $file $OutputDirectory
    }
} catch {
    $result.error = $_.Exception.Message
    throw
} finally {
    if ($started) {
        try {
            Invoke-Pktmon @("stop") | Out-Null
        } catch {
        }
    }
    if ($createdFilters) {
        try {
            Invoke-Pktmon @("filter", "remove") | Out-Null
        } catch {
        }
    }
    $result.finished_at = (Get-Date).ToString("o")
    $result | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Host ""
    Write-Host ("Resultado salvo em: {0}" -f $resultPath)
}
