$ErrorActionPreference = 'Stop'
$Repo = Split-Path $PSScriptRoot -Parent
# Read machine settings explicitly: Task Scheduler may retain an older environment.
$env:PLAYWRIGHT_BROWSERS_PATH = [Environment]::GetEnvironmentVariable('PLAYWRIGHT_BROWSERS_PATH', 'Machine')
$env:HPL_PORT = [Environment]::GetEnvironmentVariable('HPL_PORT', 'Machine')
& python "$Repo\server.py"
exit $LASTEXITCODE
