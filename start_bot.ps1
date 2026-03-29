$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-not (Test-Path (Join-Path $scriptDir '.env'))) {
    throw "Missing .env in $scriptDir"
}

$logDir = Join-Path $scriptDir 'logs'
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$logFile = Join-Path $logDir 'startup-wrapper.log'
"[$(Get-Date -Format s)] Starting telegram_jrnl_bot.py" | Out-File -FilePath $logFile -Encoding utf8 -Append

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    & py -3 (Join-Path $scriptDir 'telegram_jrnl_bot.py')
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & python (Join-Path $scriptDir 'telegram_jrnl_bot.py')
    exit $LASTEXITCODE
}

throw 'Neither py nor python was found on PATH.'
