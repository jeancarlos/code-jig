$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m harness @args install }
elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m harness @args install }
else { Write-Error "install.ps1: Python 3.11+ not found"; exit 2 }
exit $LASTEXITCODE
