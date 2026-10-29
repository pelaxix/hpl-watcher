$ErrorActionPreference = 'Stop'
$Repo = Split-Path $PSScriptRoot -Parent
# Read machine settings explicitly: Task Scheduler may retain an older environment.
$env:HPL_DATA_DIR = [Environment]::GetEnvironmentVariable('HPL_DATA_DIR', 'Machine')
$env:HPL_PORT = [Environment]::GetEnvironmentVariable('HPL_PORT', 'Machine')
& python "$Repo\server.py"
exit $LASTEXITCODE
