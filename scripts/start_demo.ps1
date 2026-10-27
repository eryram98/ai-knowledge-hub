<#
Start the demo: API on :8000 and Streamlit UI on :8501, in the background (Windows, PowerShell).

    powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1 [-Warmup]

Works from any directory. Logs go to logs\api.log and logs\ui.log, the process IDs to logs\demo.pids.
Stop with scripts\stop_demo.ps1. Never kills anything.
#>
param([switch]$Warmup)

$ErrorActionPreference = 'Stop'
$ApiPort = 8000
$UiPort = 8501
$WarmupQuestion = 'How much on-board QSPI flash does the Raspberry Pi Pico 2 have?'  # docs/DEMO_SCRIPT.md, "Warm-up"
$ReadyTimeoutSeconds = 60
$WarmupWarnSeconds = 10

function Fail($message) {
    Write-Host "ERROR: $message" -ForegroundColor Red
    exit 1
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repo

# 1. Prerequisites
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Fail ".venv not found. Create it and install dependencies (docs\SPEC.md, 'Run it'): .venv\Scripts\python -m pip install -r requirements.txt"
}
$envFile = Join-Path $repo '.env'
if (-not (Test-Path $envFile)) {
    Fail ".env not found. Copy .env.example to .env and set GEMINI_API_KEY."
}
$keyLine = Get-Content $envFile | Where-Object { $_ -match '^\s*GEMINI_API_KEY\s*=\s*\S' } | Select-Object -First 1
if (-not $keyLine) {
    Fail "GEMINI_API_KEY is empty or missing in .env. Set it, then run this again."
}

# 2. Ports must be free (report the owner, never kill it)
$busy = $false
foreach ($port in @($ApiPort, $UiPort)) {
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $proc = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
        $name = if ($proc) { $proc.ProcessName } else { 'unknown' }
        Write-Host "Port $port is in use by $name (PID $($listener.OwningProcess))." -ForegroundColor Red
        $busy = $true
    }
}
if ($busy) {
    Fail "Free the port(s) above (or run stop_demo.bat if a previous demo is still up). Nothing was started or killed."
}

# 3. Start both processes, hidden, with output in logs\
$logs = Join-Path $repo 'logs'
New-Item -ItemType Directory -Force $logs | Out-Null
$pidFile = Join-Path $logs 'demo.pids'
$env:HF_HUB_OFFLINE = '1'

$apiCmd = "`"$python`" -m uvicorn api.api_app:create_app --factory --app-dir backend\app --port $ApiPort > `"$logs\api.log`" 2>&1"
$uiCmd = "`"$python`" -m streamlit run ui\app.py --server.port $UiPort --server.headless true > `"$logs\ui.log`" 2>&1"

# cmd /c "..." keeps the redirection simple; the outer quotes are stripped by cmd's /c rule.
$api = Start-Process -FilePath $env:ComSpec -ArgumentList '/c', "`"$apiCmd`"" -WorkingDirectory $repo -WindowStyle Hidden -PassThru
$ui = Start-Process -FilePath $env:ComSpec -ArgumentList '/c', "`"$uiCmd`"" -WorkingDirectory $repo -WindowStyle Hidden -PassThru
Set-Content -Path $pidFile -Value @($api.Id, $ui.Id)
Write-Host "Started API (PID $($api.Id)) and UI (PID $($ui.Id))."

function Stop-Started {
    foreach ($id in @($api.Id, $ui.Id)) {
        & taskkill.exe /PID $id /T /F > $null 2>&1
    }
    Remove-Item $pidFile -ErrorAction SilentlyContinue
}

# 4. Wait for GET /kbs (bounded)
$kbsUrl = "http://127.0.0.1:$ApiPort/kbs"
$deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
$ready = $false
$started = Get-Date
while ((Get-Date) -lt $deadline) {
    if ($api.HasExited) { break }
    try {
        Invoke-WebRequest -Uri $kbsUrl -UseBasicParsing -TimeoutSec 3 | Out-Null
        $ready = $true
        break
    } catch {
        $elapsed = [int]((Get-Date) - $started).TotalSeconds
        Write-Host "Waiting for the API... ${elapsed}s"
        Start-Sleep -Seconds 2
    }
}
if (-not $ready) {
    Stop-Started
    Fail "The API did not answer GET /kbs within ${ReadyTimeoutSeconds}s. Both processes were stopped. See logs\api.log."
}
Write-Host "API is up: $kbsUrl" -ForegroundColor Green

# Streamlit usually finishes before the API; give it a short bounded wait too.
$uiReady = $false
for ($i = 0; $i -lt 15 -and -not $uiReady; $i++) {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$UiPort/_stcore/health" -UseBasicParsing -TimeoutSec 3 | Out-Null
        $uiReady = $true
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $uiReady) {
    Stop-Started
    Fail "The UI did not answer on port $UiPort. Both processes were stopped. See logs\ui.log."
}
Write-Host "UI is up: http://localhost:$UiPort" -ForegroundColor Green

# 5. Optional warm-up question (loads bge-small, opens the Gemini connection)
if ($Warmup) {
    Write-Host "Warm-up question (this makes 2 Gemini calls)..."
    $body = @{ question = $WarmupQuestion } | ConvertTo-Json
    $timer = [Diagnostics.Stopwatch]::StartNew()
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$ApiPort/ask" -Method Post -ContentType 'application/json' `
            -Body $body -UseBasicParsing -TimeoutSec 180 | Out-Null
        $seconds = [math]::Round($timer.Elapsed.TotalSeconds, 1)
        Write-Host "Warm-up answered in ${seconds}s."
        if ($seconds -gt $WarmupWarnSeconds) {
            Write-Host "WARNING: warm-up took more than ${WarmupWarnSeconds}s - consider the backup video." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "WARNING: warm-up failed ($($_.Exception.Message)) - check logs\api.log; consider the backup video." -ForegroundColor Yellow
    }
}

# 6. Browser and summary
Start-Process "http://localhost:$UiPort"
Write-Host ""
Write-Host "Demo is running."
Write-Host "  UI:   http://localhost:$UiPort"
Write-Host "  API:  http://127.0.0.1:$ApiPort/kbs"
Write-Host "  Logs: $logs\api.log, $logs\ui.log"
Write-Host "  Stop: double-click stop_demo.bat (or scripts\stop_demo.ps1)"
