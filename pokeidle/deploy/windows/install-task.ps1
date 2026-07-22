param(
  [string]$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
  [string]$TaskName = "PokeIdleSupervisor"
)

$ErrorActionPreference = "Stop"
$node = (Get-Command node).Source
$entry = Join-Path $ProjectDir "dist\server\main.js"
if (-not (Test-Path -LiteralPath $entry)) {
  throw "Execute npm run build antes de instalar a tarefa."
}
if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("POKEIDLE_DASHBOARD_TOKEN", "User")) -and
    [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("POKEIDLE_DASHBOARD_TOKEN", "Machine"))) {
  throw "Defina POKEIDLE_DASHBOARD_TOKEN como variável de ambiente do usuário ou da máquina."
}

$action = New-ScheduledTaskAction -Execute $node -Argument 'dist/server/main.js' -WorkingDirectory $ProjectDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType S4U -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Chromium headless isolado para Poke Idle World" -Force | Out-Null
Write-Output "Tarefa $TaskName instalada. Use Start-ScheduledTask -TaskName $TaskName para iniciar."
