param(
    [int]$Port = 5000,
    [switch]$NoBrowser,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$appDir = Join-Path $repoRoot "msfi_app"
$venvDir = Join-Path $appDir "venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$requirementsPath = Join-Path $appDir "requirements.txt"
$url = "http://127.0.0.1:$Port/"

if (-not (Test-Path $appDir)) {
    throw "App directory not found: $appDir"
}

function Get-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.14 --version *> $null
        if ($LASTEXITCODE -eq 0) {
            return @("py", "-3.14")
        }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }

    throw "Python not found. Install Python 3.14.3 and try again."
}

$pythonCmd = Get-PythonCommand

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment..."
    if ($pythonCmd.Length -gt 1) {
        & $pythonCmd[0] @($pythonCmd[1..($pythonCmd.Length - 1)]) -m venv $venvDir
    } else {
        & $pythonCmd[0] -m venv $venvDir
    }
}

if (-not $SkipInstall) {
    Write-Host "Installing/updating dependencies..."
    & $venvPython -m pip install -r $requirementsPath
}

$browserJob = $null
if (-not $NoBrowser) {
    $browserJob = Start-Job -ScriptBlock {
        param($TargetUrl)
        $deadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $deadline) {
            try {
                $resp = Invoke-WebRequest -Uri $TargetUrl -UseBasicParsing -TimeoutSec 2
                if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
                    Start-Process $TargetUrl
                    return
                }
            } catch {
                # Keep polling until Flask is reachable.
            }
            Start-Sleep -Milliseconds 500
        }

        # Fallback: still open the URL if readiness check timed out.
        Start-Process $TargetUrl
    } -ArgumentList $url
}

Write-Host ""
Write-Host "Starting MSFI Monitor at $url"
Write-Host "Press Ctrl+C to stop."
Write-Host ""

Push-Location $appDir
try {
    & $venvPython -m flask --app app run --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
    if ($browserJob) {
        Receive-Job -Job $browserJob -ErrorAction SilentlyContinue *> $null
        Remove-Job -Job $browserJob -Force -ErrorAction SilentlyContinue
    }
}
