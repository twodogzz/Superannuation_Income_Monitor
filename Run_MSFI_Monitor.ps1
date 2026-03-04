param(
    [int]$Port = 5000,
    [switch]$NoBrowser,
    [switch]$SkipInstall,
    [switch]$LanAccess,
    [string]$LanIp = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$appDir = Join-Path $repoRoot "msfi_app"
$venvDir = Join-Path $appDir "venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$requirementsPath = Join-Path $appDir "requirements.txt"
$privateIpPattern = '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)'
$bindHost = "127.0.0.1"
$url = "http://127.0.0.1:$Port/"
$lanUrl = $null

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

function Get-PreferredLanIPv4 {
    try {
        $lanRows = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -match $privateIpPattern -and
                $_.SkipAsSource -eq $false
            } |
            Sort-Object -Property InterfaceMetric, PrefixLength -Descending
        if ($lanRows) {
            return $lanRows[0].IPAddress
        }
    } catch {
        # Fall back to DNS-based lookup below.
    }

    try {
        $dnsRows = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
            Where-Object {
                $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
                $_.IPAddressToString -match $privateIpPattern
            }
        if ($dnsRows) {
            return $dnsRows[0].IPAddressToString
        }
    } catch {
        # No-op; caller handles null.
    }

    return $null
}

if ($LanAccess) {
    $bindHost = "0.0.0.0"

    if ($LanIp) {
        if ($LanIp -notmatch $privateIpPattern) {
            throw "LanIp must be a private IPv4 address (10.x.x.x, 172.16-31.x.x, or 192.168.x.x)."
        }
        $lanUrl = "http://${LanIp}:$Port/"
    } else {
        $detectedLanIp = Get-PreferredLanIPv4
        if ($detectedLanIp) {
            $lanUrl = "http://${detectedLanIp}:$Port/"
        }
    }
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
if ($LanAccess) {
    if ($lanUrl) {
        Write-Host "LAN access enabled at $lanUrl"
    } else {
        Write-Host "LAN access enabled on port $Port. Could not auto-detect private IP."
    }
    Write-Host "Home network only: ensure your router/network is trusted."
}
Write-Host "Press Ctrl+C to stop."
Write-Host ""

Push-Location $appDir
try {
    & $venvPython -m flask --app app run --host $bindHost --port $Port --no-debugger --no-reload
} finally {
    Pop-Location
    if ($browserJob) {
        Receive-Job -Job $browserJob -ErrorAction SilentlyContinue *> $null
        Remove-Job -Job $browserJob -Force -ErrorAction SilentlyContinue
    }
}
