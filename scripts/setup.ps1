# Run in PowerShell as Administrator after cloning this repository.
# Registers ONLY the frontend. Keep the existing watcher task running.
param([int]$Port = 31008)
$ErrorActionPreference = 'Stop'
$Repo = Split-Path $PSScriptRoot -Parent
$Python = (Get-Command python -ErrorAction Stop).Source
[Environment]::SetEnvironmentVariable('HPL_PORT', "$Port", 'Machine')
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Repo\scripts\run.ps1`"" -WorkingDirectory $Repo
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$Principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName 'HPL-Watcher-Frontend' -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
Start-ScheduledTask -TaskName 'HPL-Watcher-Frontend'
Write-Host "Frontend installed on http://127.0.0.1:$Port. Direct HPL checks enabled; see README.md for Playwright browser setup."
