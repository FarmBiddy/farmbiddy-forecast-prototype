# Start FarmBiddy web app (works when uvicorn.exe is not on PATH)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$logPath = Join-Path $PSScriptRoot "debug-fddef3.log"
$timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
$uvicornExe = Get-Command uvicorn -ErrorAction SilentlyContinue
$scriptsDir = Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.14-64\Scripts"
$scriptsUvicorn = Join-Path $scriptsDir "uvicorn.exe"

#region agent log
@{
    sessionId = "fddef3"
    runId = "start-script"
    hypothesisId = "H1-H4"
    location = "start.ps1:env-check"
    message = "Startup environment diagnostics"
    data = @{
        cwd = (Get-Location).Path
        pythonPath = if ($pythonCmd) { $pythonCmd.Source } else { $null }
        uvicornOnPath = [bool]$uvicornExe
        scriptsUvicornExists = Test-Path $scriptsUvicorn
        launchMode = "python -m uvicorn"
    }
    timestamp = $timestamp
} | ConvertTo-Json -Compress | Add-Content -Path $logPath -Encoding utf8
#endregion

if (-not $pythonCmd) {
    Write-Error "Python not found. Install Python 3 and run: python -m pip install -r requirements.txt"
    exit 1
}

Write-Host "Starting FarmBiddy at http://127.0.0.1:8000 (API docs: /docs)"
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
