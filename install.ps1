$ErrorActionPreference = "Stop"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Error "install.ps1: git not found (winget install --id Git.Git -e)"; exit 2 }
$env:PYTHONPATH = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m codejig @args install }
elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m codejig @args install }
else { Write-Error "install.ps1: Python 3.11+ not found"; exit 2 }
exit $LASTEXITCODE
