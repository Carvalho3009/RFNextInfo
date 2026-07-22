[CmdletBinding()]
param(
    [string]$CaptureInterface,
    [string]$OutputDirectory,
    [ValidateRange(0, 86400)]
    [int]$DurationSeconds = 0,
    [string]$ControlFile,
    [string]$MarketCsvPath,
    [string]$DecoderPath,
    [string]$ItemsCsvPath,
    [switch]$SkipMarketCsv,
    [switch]$SkipMarketDatabase,
    [switch]$ContinuousMarket,
    [switch]$NoHotkeys,
    [ValidateRange(5, 3600)]
    [int]$MarketScanSeconds = 15,
    [switch]$Gui,
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $PSScriptRoot 'captures' }
if (-not $MarketCsvPath) { $MarketCsvPath = Join-Path $OutputDirectory 'market.csv' }
if (-not $ItemsCsvPath) { $ItemsCsvPath = Join-Path $PSScriptRoot 'analysis\1.28.5\exports\auction_eligible_items.csv' }
if (-not $DecoderPath) { $DecoderPath = Join-Path $env:USERPROFILE 'OneDrive\Documentos\RF NEXt\rfnext_frame_decode.py' }

if (-not ('CaptureHotkeys' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class CaptureHotkeys
{
    [StructLayout(LayoutKind.Sequential)]
    public struct Point { public int X; public int Y; }

    [StructLayout(LayoutKind.Sequential)]
    public struct Message
    {
        public IntPtr Window;
        public uint Id;
        public UIntPtr WParam;
        public IntPtr LParam;
        public uint Time;
        public Point Cursor;
    }

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool RegisterHotKey(IntPtr window, int id, uint modifiers, uint key);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool UnregisterHotKey(IntPtr window, int id);

    [DllImport("user32.dll")]
    public static extern bool PeekMessage(out Message message, IntPtr window, uint min, uint max, uint remove);
}
'@
}

$hotkeys = @{
    1001 = @{ Event = 'EXP';     Key = 0x45; Display = 'Ctrl+Alt+E' }
    1002 = @{ Event = 'MOB';     Key = 0x4D; Display = 'Ctrl+Alt+M' }
    1003 = @{ Event = 'LOOT';    Key = 0x4C; Display = 'Ctrl+Alt+L' }
    1004 = @{ Event = 'LEILAO';  Key = 0x41; Display = 'Ctrl+Alt+A' }
    1005 = @{ Event = 'ENCERRAR'; Key = 0x53; Display = 'Ctrl+Alt+S' }
}

function Register-CaptureHotkeys {
    $registered = @()
    $modifiers = [uint32](0x0001 -bor 0x0002 -bor 0x4000) # Alt + Ctrl + sem repetição
    foreach ($entry in $hotkeys.GetEnumerator()) {
        if ($ContinuousMarket -and $entry.Value.Event -ne 'ENCERRAR') { continue }
        if (-not [CaptureHotkeys]::RegisterHotKey([IntPtr]::Zero, [int]$entry.Key, $modifiers, [uint32]$entry.Value.Key)) {
            foreach ($id in $registered) { [void][CaptureHotkeys]::UnregisterHotKey([IntPtr]::Zero, $id) }
            throw "O atalho $($entry.Value.Display) já está em uso por outro programa."
        }
        $registered += [int]$entry.Key
    }
}

function Unregister-CaptureHotkeys {
    foreach ($id in $hotkeys.Keys) { [void][CaptureHotkeys]::UnregisterHotKey([IntPtr]::Zero, [int]$id) }
}

function Write-CaptureEvent {
    param(
        [System.IO.StreamWriter]$Writer,
        [ref]$Sequence,
        [string]$Event,
        [string]$Hotkey,
        [long]$ClockOffset,
        [long]$ClockUncertainty,
        [long]$CaptureStartHost
    )

    $hostNow = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $Sequence.Value++
    $elapsed = $hostNow - $CaptureStartHost
    $localTime = [DateTimeOffset]::Now.ToString('o', [Globalization.CultureInfo]::InvariantCulture)
    $Writer.WriteLine(('{0},{1},{2},{3},{4},{5},{6}' -f $Sequence.Value, $Event, ($hostNow + $ClockOffset), $localTime, $elapsed, $Hotkey, $ClockUncertainty))
    Write-Host ('[{0:N3}s] {1} registrado' -f ($elapsed / 1000), $Event) -ForegroundColor Green
}

function Get-NewControlCommands {
    param([string]$Path, [ref]$Index)

    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return @() }
    try {
        $lines = @([IO.File]::ReadAllLines($Path))
        if ($Index.Value -ge $lines.Count) { return @() }
        $commands = @($lines[$Index.Value..($lines.Count - 1)])
        $Index.Value = $lines.Count
        $commands
    } catch {
        @() # ponytail: arquivo pode estar aberto pela GUI; o próximo ciclo tenta novamente
    }
}

function Export-MarketCapture {
    param([string]$PcapPath, [switch]$Quiet)

    if (-not (Test-Path -LiteralPath $DecoderPath)) { throw "Decodificador não encontrado: $DecoderPath" }
    if (-not (Test-Path -LiteralPath $ItemsCsvPath)) { throw "Cadastro de itens não encontrado: $ItemsCsvPath" }
    $python = Get-Command py.exe -ErrorAction SilentlyContinue
    $pythonArgs = @('-3')
    if (-not $python) {
        $python = Get-Command python.exe -ErrorAction Stop
        $pythonArgs = @()
    }
    $jsonPath = [IO.Path]::ChangeExtension($PcapPath, '.exchange.jsonl')
    $result = & $python.Source @pythonArgs $DecoderPath $PcapPath --pcap --exchange-only --items-csv $ItemsCsvPath --market-csv $MarketCsvPath --output $jsonPath 2>&1
    if ($LASTEXITCODE -ne 0) { throw (($result | Out-String).Trim()) }
    $rowCount = @(Import-Csv -LiteralPath $MarketCsvPath).Count
    if (-not $Quiet) { Write-Host "CSV do site: $MarketCsvPath ($rowCount registros)" -ForegroundColor Green }
    $rowCount
}

function Publish-MarketDatabase {
    param([string]$PcapPath, [string]$SourceId)

    $docker = Get-Command docker.exe -ErrorAction SilentlyContinue
    if (-not $docker) { Write-Warning 'Docker não encontrado; o CSV foi salvo, mas o banco do site não foi atualizado.'; return }
    $containers = @(& $docker.Source ps --filter 'label=com.docker.compose.project=karvalho' --filter 'label=com.docker.compose.service=rfnext' --filter 'label=com.docker.compose.oneoff=False' --format '{{.ID}}')
    if ($containers.Count -eq 0) { Write-Warning 'Site rfnext não está em execução; o CSV foi salvo, mas o banco não foi atualizado.'; return }
    $container = $containers[0]
    $remotePath = "/tmp/rfnext-market-$PID.csv"
    try {
        & $docker.Source cp $MarketCsvPath "${container}:$remotePath" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao copiar o CSV para o site.' }
        $capturedAt = (Get-Item -LiteralPath $PcapPath).LastWriteTimeUtc.ToString('o')
        $result = & $docker.Source exec $container python3 server.py --import-market $remotePath --captured-at $capturedAt --source-id $SourceId 2>&1
        if ($LASTEXITCODE -ne 0) { throw (($result | Out-String).Trim()) }
        Write-Host "Banco do site atualizado: $(($result | Out-String).Trim())" -ForegroundColor Green
    } finally {
        & $docker.Source exec $container rm -f $remotePath 2>$null | Out-Null
    }
}

function Connect-EventButton {
    param($Button, [string]$EventName, $State, $EventsView, $CountsLabel, $LastTimestamp)

    $handler = {
        if ($State.ControlFile) {
            [IO.File]::AppendAllText($State.ControlFile, "$EventName`r`n", [Text.UTF8Encoding]::new($false))
        }
        $now = [DateTimeOffset]::Now
        $elapsed = $State.Stopwatch.Elapsed
        $State.Counts[$EventName]++
        $item = [Windows.Forms.ListViewItem]::new($now.ToString('HH:mm:ss.fff'))
        [void]$item.SubItems.Add(('{0:hh\:mm\:ss\.fff}' -f $elapsed))
        [void]$item.SubItems.Add($(if ($EventName -eq 'LEILAO') { 'LEILÃO' } else { $EventName }))
        [void]$item.SubItems.Add([string]$State.Counts[$EventName])
        $EventsView.Items.Insert(0, $item)
        $shownEvent = if ($EventName -eq 'LEILAO') { 'LEILÃO' } else { $EventName }
        $LastTimestamp.Text = "Último timestamp: $($now.ToString('HH:mm:ss.fff')) — $shownEvent"
        $CountsLabel.Text = "EXP $($State.Counts.EXP)   •   MOB $($State.Counts.MOB)   •   LOOT $($State.Counts.LOOT)   •   LEILÃO $($State.Counts.LEILAO)"
    }.GetNewClosure()
    $Button.Add_Click($handler)
}

function Show-CaptureGui {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [Windows.Forms.Application]::EnableVisualStyles()
    $captureScriptPath = $PSCommandPath
    $captureOutputDirectory = $OutputDirectory

    $form = [Windows.Forms.Form]::new()
    $form.Text = 'RF Next — Captura de tráfego'
    $form.StartPosition = 'CenterScreen'
    $form.ClientSize = [Drawing.Size]::new(720, 500)
    $form.MinimumSize = [Drawing.Size]::new(736, 539)
    $form.Font = [Drawing.Font]::new('Segoe UI', 10)

    $title = [Windows.Forms.Label]::new()
    $title.Text = 'Captura PCAP com marcadores sincronizados'
    $title.Font = [Drawing.Font]::new('Segoe UI Semibold', 16)
    $title.AutoSize = $true
    $title.Location = [Drawing.Point]::new(20, 16)
    $form.Controls.Add($title)

    $status = [Windows.Forms.Label]::new()
    $status.Text = 'Pronto. Inicie a captura antes de abrir a tela Mercado no RF Next.'
    $status.AutoSize = $true
    $status.Location = [Drawing.Point]::new(22, 55)
    $form.Controls.Add($status)

    $elapsedLabel = [Windows.Forms.Label]::new()
    $elapsedLabel.Text = '00:00:00.000'
    $elapsedLabel.Font = [Drawing.Font]::new('Consolas', 18, [Drawing.FontStyle]::Bold)
    $elapsedLabel.AutoSize = $true
    $elapsedLabel.Location = [Drawing.Point]::new(548, 16)
    $form.Controls.Add($elapsedLabel)

    $progress = [Windows.Forms.ProgressBar]::new()
    $progress.Location = [Drawing.Point]::new(22, 82)
    $progress.Size = [Drawing.Size]::new(676, 18)
    $progress.Style = 'Blocks'
    $form.Controls.Add($progress)

    function New-GuiButton([string]$text, [int]$x, [int]$y, [int]$width = 126) {
        $button = [Windows.Forms.Button]::new()
        $button.Text = $text
        $button.Location = [Drawing.Point]::new($x, $y)
        $button.Size = [Drawing.Size]::new($width, 42)
        $form.Controls.Add($button)
        $button
    }

    $startButton = New-GuiButton '▶ Iniciar captura' 22 118 160
    $stopButton = New-GuiButton '■ Encerrar' 194 118 130
    $expButton = New-GuiButton 'EXP' 22 178
    $mobButton = New-GuiButton 'MOB' 160 178
    $lootButton = New-GuiButton 'LOOT' 298 178
    $auctionButton = New-GuiButton 'LEILÃO' 436 178
    $stopButton.Enabled = $false
    foreach ($button in @($expButton, $mobButton, $lootButton, $auctionButton)) { $button.Enabled = $false }

    $countsLabel = [Windows.Forms.Label]::new()
    $countsLabel.Text = 'EXP 0   •   MOB 0   •   LOOT 0   •   LEILÃO 0'
    $countsLabel.AutoSize = $true
    $countsLabel.Location = [Drawing.Point]::new(22, 232)
    $form.Controls.Add($countsLabel)

    $lastTimestamp = [Windows.Forms.Label]::new()
    $lastTimestamp.Text = 'Último timestamp: —'
    $lastTimestamp.AutoSize = $true
    $lastTimestamp.Location = [Drawing.Point]::new(22, 258)
    $form.Controls.Add($lastTimestamp)

    $eventsView = [Windows.Forms.ListView]::new()
    $eventsView.Location = [Drawing.Point]::new(22, 288)
    $eventsView.Size = [Drawing.Size]::new(676, 178)
    $eventsView.Anchor = 'Top,Bottom,Left,Right'
    $eventsView.View = 'Details'
    $eventsView.FullRowSelect = $true
    $eventsView.GridLines = $true
    [void]$eventsView.Columns.Add('Hora', 130)
    [void]$eventsView.Columns.Add('Decorrido', 130)
    [void]$eventsView.Columns.Add('Evento', 150)
    [void]$eventsView.Columns.Add('Quantidade', 120)
    $form.Controls.Add($eventsView)

    $state = [pscustomobject]@{
        Process = $null
        Stopwatch = [Diagnostics.Stopwatch]::new()
        ControlFile = $null
        Counts = @{ EXP = 0; MOB = 0; LOOT = 0; LEILAO = 0 }
        Closing = $false
    }

    $startButton.Add_Click({
        $state.ControlFile = Join-Path ([IO.Path]::GetTempPath()) ("rfnext-capture-$([guid]::NewGuid().ToString('N')).commands")
        [IO.File]::WriteAllText($state.ControlFile, '', [Text.UTF8Encoding]::new($false))
        $state.Counts = @{ EXP = 0; MOB = 0; LOOT = 0; LEILAO = 0 }
        $eventsView.Items.Clear()
        $countsLabel.Text = 'EXP 0   •   MOB 0   •   LOOT 0   •   LEILÃO 0'
        $lastTimestamp.Text = 'Último timestamp: —'

        $powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
        $info = [Diagnostics.ProcessStartInfo]::new()
        $info.FileName = $powershell
        $continuousArgs = if ($ContinuousMarket) { " -ContinuousMarket -MarketScanSeconds $MarketScanSeconds" } else { '' }
        $info.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$captureScriptPath`" -ControlFile `"$($state.ControlFile)`" -OutputDirectory `"$captureOutputDirectory`"$continuousArgs"
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $false
        $info.RedirectStandardError = $true
        $state.Process = [Diagnostics.Process]::Start($info)
        $state.Stopwatch.Restart()
        $status.Text = 'Preparando Npcap... espere “Capturando” antes de abrir o Mercado.'
        $progress.Style = 'Marquee'
        $progress.MarqueeAnimationSpeed = 25
        $startButton.Enabled = $false
        $stopButton.Enabled = $true
        foreach ($button in @($expButton, $mobButton, $lootButton, $auctionButton)) { $button.Enabled = $true }
    }.GetNewClosure())

    Connect-EventButton $expButton 'EXP' $state $eventsView $countsLabel $lastTimestamp
    Connect-EventButton $mobButton 'MOB' $state $eventsView $countsLabel $lastTimestamp
    Connect-EventButton $lootButton 'LOOT' $state $eventsView $countsLabel $lastTimestamp
    Connect-EventButton $auctionButton 'LEILAO' $state $eventsView $countsLabel $lastTimestamp

    $stopButton.Add_Click({
        if ($state.ControlFile) {
            [IO.File]::AppendAllText($state.ControlFile, "ENCERRAR`r`n", [Text.UTF8Encoding]::new($false))
        }
        $stopButton.Enabled = $false
        $status.Text = 'Finalizando e copiando o PCAP...'
    }.GetNewClosure())

    $timer = [Windows.Forms.Timer]::new()
    $timer.Interval = 100
    $timer.Add_Tick({
        if (-not $state.Process) { return }
        if (-not $state.Process.HasExited) {
            $elapsed = $state.Stopwatch.Elapsed
            $elapsedLabel.Text = ('{0:hh\:mm\:ss\.fff}' -f $elapsed)
            if ($status.Text -like 'Preparando*' -and (Get-Content -LiteralPath $state.ControlFile -ErrorAction SilentlyContinue) -contains 'READY') {
                $status.Text = 'Capturando — agora abra o Mercado no RF Next.'
            }
            return
        }

        $state.Stopwatch.Stop()
        $progress.Style = 'Blocks'
        $progress.Value = 0
        $startButton.Enabled = $true
        $stopButton.Enabled = $false
        foreach ($button in @($expButton, $mobButton, $lootButton, $auctionButton)) { $button.Enabled = $false }
        $stderr = $state.Process.StandardError.ReadToEnd().Trim()
        $exitCode = $state.Process.ExitCode
        if ($exitCode -eq 0) {
            $latest = Get-ChildItem -LiteralPath $captureOutputDirectory -Filter 'rfnext-pc-*.pcap' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            $json = if ($latest) { [IO.Path]::ChangeExtension($latest.FullName, '.exchange.jsonl') } else { '' }
            $market = Join-Path $captureOutputDirectory 'market.csv'
            $status.Text = if ($json -and (Test-Path -LiteralPath $json) -and (Test-Path -LiteralPath $market)) {
                "Concluído: market.csv com $(@(Import-Csv -LiteralPath $market).Count) registros"
            } elseif ($latest) {
                'Captura salva; nenhuma lista completa do Mercado foi encontrada.'
            } else { 'Captura concluída.' }
        } else {
            $status.Text = if ($stderr) { "Erro: $stderr" } else { "Capturador encerrou com código $exitCode." }
            [Windows.Forms.MessageBox]::Show($status.Text, 'Falha na captura', 'OK', 'Error') | Out-Null
        }
        $state.Process.Dispose()
        $state.Process = $null
        if ($state.ControlFile -and (Test-Path -LiteralPath $state.ControlFile)) { Remove-Item -LiteralPath $state.ControlFile -Force }
        $state.ControlFile = $null
        if ($state.Closing) { $form.Close() }
    }.GetNewClosure())
    $timer.Start()

    $form.Add_FormClosing({
        param($sender, $eventArgs)
        if ($state.Process -and -not $state.Process.HasExited) {
            if (-not $state.Closing) {
                $answer = [Windows.Forms.MessageBox]::Show('Encerrar a captura e salvar antes de fechar?', 'Captura em andamento', 'YesNo', 'Question')
                if ($answer -eq 'Yes') {
                    $state.Closing = $true
                    [IO.File]::AppendAllText($state.ControlFile, "ENCERRAR`r`n", [Text.UTF8Encoding]::new($false))
                    $status.Text = 'Finalizando e copiando o PCAP...'
                }
            }
            $eventArgs.Cancel = $true
        }
    }.GetNewClosure())

    [void]$form.ShowDialog()
    $timer.Dispose()
    $form.Dispose()
}

function Invoke-SelfTest {
    if (-not (Test-Path -LiteralPath 'C:\Program Files\Wireshark\dumpcap.exe')) { throw 'dumpcap não encontrado.' }
    if (-not ('CaptureHotkeys' -as [type]) -or $hotkeys.Count -ne 5) { throw 'Falha ao preparar atalhos globais.' }
    if ($hotkeys[1004].Event -ne 'LEILAO') { throw 'Falha ao consultar marcador por atalho.' }
    try { Register-CaptureHotkeys } finally { Unregister-CaptureHotkeys }
    Add-Type -AssemblyName System.Windows.Forms
    $testState = [pscustomobject]@{
        ControlFile = $null
        Counts = @{ EXP = 0; MOB = 0; LOOT = 0; LEILAO = 0 }
        Stopwatch = [Diagnostics.Stopwatch]::StartNew()
    }
    $testButton = [Windows.Forms.Button]::new()
    $testEventsView = [Windows.Forms.ListView]::new()
    $testCountsLabel = [Windows.Forms.Label]::new()
    $testLastTimestamp = [Windows.Forms.Label]::new()
    Connect-EventButton $testButton 'EXP' $testState $testEventsView $testCountsLabel $testLastTimestamp
    $testButton.PerformClick()
    if ($testState.Counts.EXP -ne 1 -or $testEventsView.Items.Count -ne 1 -or $testCountsLabel.Text -notlike 'EXP 1*') {
        throw 'Falha no callback dos marcadores da interface.'
    }
    $testButton.Dispose()
    $testEventsView.Dispose()
    $testCountsLabel.Dispose()
    $testLastTimestamp.Dispose()
    'Self-test OK'
}

if ($SelfTest) {
    Invoke-SelfTest
    exit 0
}

if ($Gui) {
    Show-CaptureGui
    exit 0
}

$dumpcap = 'C:\Program Files\Wireshark\dumpcap.exe'
if (-not (Test-Path -LiteralPath $dumpcap)) { throw 'dumpcap não encontrado. Instale o Wireshark com Npcap.' }

if ($CaptureInterface) {
    $captureDevice = $CaptureInterface
} else {
    $route = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' |
        Sort-Object RouteMetric, InterfaceMetric |
        Select-Object -First 1
    if (-not $route) { throw 'Não foi possível identificar a interface padrão da Internet.' }
    $adapter = Get-NetAdapter -InterfaceIndex $route.InterfaceIndex
    $interfaceGuid = [guid]$adapter.InterfaceGuid
    $captureDevice = "\Device\NPF_$($interfaceGuid.ToString('B').ToUpperInvariant())"
}
if ($captureDevice.Contains('"')) { throw 'Nome de interface inválido.' }

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$fileName = "rfnext-pc-$stamp.pcap"
$localPath = Join-Path (Resolve-Path -LiteralPath $OutputDirectory) $fileName
$eventsPath = [IO.Path]::ChangeExtension($localPath, '.events.csv')
$captureStarted = $false
$captureProcess = $null
$hotkeysRegistered = $false
$writer = $null
$stopLogged = $false
$sequence = 0
try {
    if (-not $NoHotkeys) {
        Register-CaptureHotkeys
        $hotkeysRegistered = $true
    }
    $clock = @{ Offset = 0L; Uncertainty = 1L }
    $processInfo = [Diagnostics.ProcessStartInfo]::new()
    $processInfo.FileName = $dumpcap
    $captureFilter = if ($ContinuousMarket) { 'tcp port 12020' } else { 'tcp or udp' }
    $processInfo.Arguments = "-i `"$captureDevice`" -f `"$captureFilter`" -s 0 -F pcap -w `"$localPath`""
    $processInfo.UseShellExecute = $true
    $processInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $captureProcess = [Diagnostics.Process]::Start($processInfo)
    $captureStarted = $true
    for ($attempt = 0; $attempt -lt 20 -and -not (Test-Path -LiteralPath $localPath); $attempt++) {
        if ($captureProcess.HasExited) { throw "dumpcap encerrou com código $($captureProcess.ExitCode)." }
        Start-Sleep -Milliseconds 100
    }
    if ($captureProcess.HasExited) { throw "dumpcap encerrou com código $($captureProcess.ExitCode)." }
    $captureStartHost = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    if ($ControlFile) { [IO.File]::AppendAllText($ControlFile, "READY`r`n", [Text.UTF8Encoding]::new($false)) }

    $writer = [IO.StreamWriter]::new($eventsPath, $false, [Text.UTF8Encoding]::new($false))
    $writer.AutoFlush = $true
    $writer.WriteLine('sequence,event,pcap_epoch_ms,local_time,elapsed_ms,hotkey,clock_uncertainty_ms')
    Write-CaptureEvent -Writer $writer -Sequence ([ref]$sequence) -Event 'CAPTURA_INICIO' -Hotkey '' -ClockOffset $clock.Offset -ClockUncertainty $clock.Uncertainty -CaptureStartHost $captureStartHost

    Write-Host "Capturando TCP/UDP no Windows pela interface $captureDevice."
    Write-Host "PCAP: $localPath"
    Write-Host "Eventos: $eventsPath"
    Write-Host ''
    Write-Host 'Ctrl+Alt+E = EXP    Ctrl+Alt+M = MOB    Ctrl+Alt+L = LOOT' -ForegroundColor Cyan
    Write-Host 'Ctrl+Alt+A = LEILÃO Ctrl+Alt+S = ENCERRAR' -ForegroundColor Cyan

    $deadline = if ($DurationSeconds -gt 0) { [DateTimeOffset]::UtcNow.AddSeconds($DurationSeconds) } else { $null }
    $message = New-Object CaptureHotkeys+Message
    $controlIndex = 0
    $lastMarketHash = $null
    $nextMarketScan = [DateTimeOffset]::UtcNow.AddSeconds($MarketScanSeconds)
    $running = $true
    while ($running) {
        if ($captureProcess.HasExited) { throw "dumpcap encerrou inesperadamente com código $($captureProcess.ExitCode)." }
        while ([CaptureHotkeys]::PeekMessage([ref]$message, [IntPtr]::Zero, 0, 0, 1)) {
            if ($message.Id -ne 0x0312) { continue }
            $id = [int]$message.WParam.ToUInt32()
            if ($id -eq 1005) {
                Write-CaptureEvent -Writer $writer -Sequence ([ref]$sequence) -Event 'CAPTURA_FIM' -Hotkey $hotkeys[$id].Display -ClockOffset $clock.Offset -ClockUncertainty $clock.Uncertainty -CaptureStartHost $captureStartHost
                $stopLogged = $true
                $running = $false
                break
            }
            if ($hotkeys.Contains($id)) {
                Write-CaptureEvent -Writer $writer -Sequence ([ref]$sequence) -Event $hotkeys[$id].Event -Hotkey $hotkeys[$id].Display -ClockOffset $clock.Offset -ClockUncertainty $clock.Uncertainty -CaptureStartHost $captureStartHost
            }
        }
        foreach ($command in @(Get-NewControlCommands -Path $ControlFile -Index ([ref]$controlIndex))) {
            $command = $command.Trim().ToUpperInvariant()
            if ($command -eq 'ENCERRAR') {
                Write-CaptureEvent -Writer $writer -Sequence ([ref]$sequence) -Event 'CAPTURA_FIM' -Hotkey 'INTERFACE' -ClockOffset $clock.Offset -ClockUncertainty $clock.Uncertainty -CaptureStartHost $captureStartHost
                $stopLogged = $true
                $running = $false
                break
            }
            if ($command -in @('EXP', 'MOB', 'LOOT', 'LEILAO')) {
                Write-CaptureEvent -Writer $writer -Sequence ([ref]$sequence) -Event $command -Hotkey 'INTERFACE' -ClockOffset $clock.Offset -ClockUncertainty $clock.Uncertainty -CaptureStartHost $captureStartHost
            }
        }
        if ($ContinuousMarket -and [DateTimeOffset]::UtcNow -ge $nextMarketScan) {
            try {
                $marketRows = Export-MarketCapture -PcapPath $localPath -Quiet
                $marketHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $MarketCsvPath).Hash.ToLowerInvariant()
                # ponytail: estados idênticos na mesma sessão não geram outra fotografia; registrar heartbeat se isso virar requisito.
                if ($marketRows -and $marketHash -ne $lastMarketHash) {
                    if (-not $SkipMarketDatabase) { Publish-MarketDatabase -PcapPath $localPath -SourceId "live-$stamp-$marketHash" }
                    $lastMarketHash = $marketHash
                }
            } catch { }
            $nextMarketScan = [DateTimeOffset]::UtcNow.AddSeconds($MarketScanSeconds)
        }
        if ($deadline -and [DateTimeOffset]::UtcNow -ge $deadline) { $running = $false }
        Start-Sleep -Milliseconds 25
    }

    if (-not $stopLogged) {
        Write-CaptureEvent -Writer $writer -Sequence ([ref]$sequence) -Event 'CAPTURA_FIM' -Hotkey 'TEMPO/CANCELAMENTO' -ClockOffset $clock.Offset -ClockUncertainty $clock.Uncertainty -CaptureStartHost $captureStartHost
        $stopLogged = $true
    }
}
finally {
    if ($hotkeysRegistered) { Unregister-CaptureHotkeys }
    if ($writer) { $writer.Dispose() }
    if ($captureStarted) {
        Write-Host 'Encerrando captura...'
        if (-not $captureProcess.HasExited) { $captureProcess.Kill() }
        $captureProcess.WaitForExit()
        $captureProcess.Dispose()
        Start-Sleep -Milliseconds 300

        if (-not (Test-Path -LiteralPath $localPath)) {
            [byte[]]$emptyPcap = 0xd4,0xc3,0xb2,0xa1,0x02,0x00,0x04,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xff,0xff,0x00,0x00,0x01,0x00,0x00,0x00
            [IO.File]::WriteAllBytes($localPath, $emptyPcap)
        }
        $file = Get-Item -LiteralPath $localPath
        if ($file.Length -lt 24) { throw 'O PCAP copiado está vazio ou inválido.' }
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $localPath).Hash.ToLowerInvariant()

        Write-Host "Captura salva: $localPath"
        Write-Host "Eventos salvos: $eventsPath"
        Write-Host "Tamanho: $($file.Length) bytes"
        Write-Host "SHA-256: $hash"
        if (-not $SkipMarketCsv) {
            $marketRows = $null
            try { $marketRows = Export-MarketCapture -PcapPath $localPath }
            catch { Write-Warning "CSV do Mercado não foi atualizado: $($_.Exception.Message)" }
            if ($marketRows -and -not $SkipMarketDatabase) {
                $marketHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $MarketCsvPath).Hash.ToLowerInvariant()
                $sourceId = if ($ContinuousMarket) { "live-$stamp-$marketHash" } else { $hash }
                try { Publish-MarketDatabase -PcapPath $localPath -SourceId $sourceId }
                catch { Write-Warning "Banco do Mercado não foi atualizado: $($_.Exception.Message)" }
            }
        }
    }
}
