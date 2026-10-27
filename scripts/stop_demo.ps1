<#
Stop the demo started by start_demo.ps1: only the PIDs in logs\demo.pids and their child processes.

    powershell -ExecutionPolicy Bypass -File scripts\stop_demo.ps1
#>
$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pidFile = Join-Path $repo 'logs\demo.pids'

if (-not (Test-Path $pidFile)) {
    Write-Host "No logs\demo.pids: nothing to stop."
    exit 0
}

# start_demo.ps1 records the cmd.exe wrappers; a reused PID would be some other program, so check the name.
$expected = @('cmd', 'python', 'pythonw')
foreach ($line in Get-Content $pidFile) {
    if ($line -notmatch '^\s*(\d+)\s*$') { continue }
    $id = [int]$Matches[1]
    $proc = Get-Process -Id $id -ErrorAction SilentlyContinue
    if (-not $proc) {
        Write-Host "PID $id already gone."
    } elseif ($expected -notcontains $proc.ProcessName) {
        Write-Host "PID $id is now '$($proc.ProcessName)', not a demo process: left alone." -ForegroundColor Yellow
    } else {
        & taskkill.exe /PID $id /T /F > $null 2>&1
        Write-Host "Stopped PID $id ($($proc.ProcessName)) and its children."
    }
}

Remove-Item $pidFile
Write-Host "Demo stopped."
