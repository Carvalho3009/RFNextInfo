param([string]$TaskName = "PokeIdleSupervisor")
$ErrorActionPreference = "Stop"
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Output "Tarefa $TaskName removida. Perfis e logs foram preservados."
