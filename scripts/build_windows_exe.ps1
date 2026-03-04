param(
    [int]$Port = 5000,
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EntryPoint = Join-Path $ProjectRoot "msfi_app\windows_launcher.py"
$Requirements = Join-Path $ProjectRoot "msfi_app\requirements.txt"
$AppVenvPython = Join-Path $ProjectRoot "msfi_app\venv\Scripts\python.exe"
$VenvDir = Join-Path $ProjectRoot ".venv-build"
$BuildVenvPython = Join-Path $VenvDir "Scripts\python.exe"
$DistDir = Join-Path $ProjectRoot "dist\windows"
$WorkDir = Join-Path $ProjectRoot "build\pyinstaller"
$SpecDir = Join-Path $ProjectRoot "build\spec"
$TemplateSource = Join-Path $ProjectRoot "msfi_app\templates"
$StaticSource = Join-Path $ProjectRoot "msfi_app\static"

if (!(Test-Path $EntryPoint)) {
    throw "Missing entry point: $EntryPoint"
}
if (!(Test-Path $TemplateSource)) {
    throw "Missing templates folder: $TemplateSource"
}
if (!(Test-Path $StaticSource)) {
    throw "Missing static folder: $StaticSource"
}

function Test-PythonExe([string]$Path) {
    if (!(Test-Path $Path)) { return $false }
    & $Path -c "import sys; print(sys.version)" *> $null
    return ($LASTEXITCODE -eq 0)
}

if (Test-PythonExe $AppVenvPython) {
    $PythonExe = $AppVenvPython
    Write-Host "Using existing app virtual environment: $AppVenvPython"
} else {
    if (!(Test-PythonExe $BuildVenvPython)) {
        if (Test-Path $VenvDir) {
            Write-Host "Removing incomplete build venv: $VenvDir"
            Remove-Item -Recurse -Force $VenvDir
        }
        Write-Host "Creating build virtual environment..."
        python -m venv $VenvDir
    }
    if (!(Test-PythonExe $BuildVenvPython)) {
        throw "Build Python not available at $BuildVenvPython. Create a venv manually and rerun."
    }
    $PythonExe = $BuildVenvPython
}

Write-Host "Installing build dependencies..."
& $PythonExe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed with exit code $LASTEXITCODE." }
& $PythonExe -m pip install -r $Requirements pyinstaller
if ($LASTEXITCODE -ne 0) { throw "dependency installation failed with exit code $LASTEXITCODE." }

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
New-Item -ItemType Directory -Force -Path $SpecDir | Out-Null

$ModeArg = if ($OneFile) { "--onefile" } else { "--onedir" }
$TemplateData = "$TemplateSource;templates"
$StaticData = "$StaticSource;static"

Write-Host "Building Windows executable..."
& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    $ModeArg `
    --name "MSFI_Monitor" `
    --distpath $DistDir `
    --workpath $WorkDir `
    --specpath $SpecDir `
    --add-data $TemplateData `
    --add-data $StaticData `
    $EntryPoint
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }

$ExePath = if ($OneFile) {
    Join-Path $DistDir "MSFI_Monitor.exe"
} else {
    Join-Path $DistDir "MSFI_Monitor\MSFI_Monitor.exe"
}

Write-Host ""
Write-Host "Build complete."
Write-Host "Executable: $ExePath"
Write-Host "Run with LAN access (always enabled by launcher):"
Write-Host "  `$env:MSFI_PORT=$Port; `"$ExePath`""
