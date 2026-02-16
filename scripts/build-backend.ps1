param(
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$serviceDir = Join-Path $repoRoot "service"
$serviceSrc = Join-Path $serviceDir "src"
$entryScript = Join-Path $serviceSrc "voice_text_organizer\service_entry.py"

$distRoot = Join-Path $repoRoot "dist"
$distDir = Join-Path $distRoot "backend"
$pyiWorkDir = Join-Path $distRoot ".pyinstaller\backend\work"
$pyiSpecDir = Join-Path $distRoot ".pyinstaller\backend\spec"

function Resolve-PythonCommand {
    param([string]$RepoRoot)

    if ($env:VTO_PYTHON_EXE -and (Test-Path $env:VTO_PYTHON_EXE)) {
        return (Resolve-Path $env:VTO_PYTHON_EXE).Path
    }

    $venvCandidates = @(
        (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
        (Join-Path $RepoRoot "service\.venv\Scripts\python.exe")
    )
    foreach ($candidate in $venvCandidates) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }

    throw "Python runtime not found. Install Python or set VTO_PYTHON_EXE."
}

$pythonExe = Resolve-PythonCommand -RepoRoot $repoRoot

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
New-Item -ItemType Directory -Force -Path $pyiWorkDir | Out-Null
New-Item -ItemType Directory -Force -Path $pyiSpecDir | Out-Null

if (-not (Test-Path $entryScript)) {
    throw "Backend entry script not found: $entryScript"
}

if (-not $SkipDependencyInstall) {
    & $pythonExe -m pip install --upgrade pip
    & $pythonExe -m pip install pyinstaller
}

& $pythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name "TypelessService" `
    --paths $serviceSrc `
    --collect-all sounddevice `
    --distpath $distDir `
    --workpath $pyiWorkDir `
    --specpath $pyiSpecDir `
    $entryScript

$bundleDir = Join-Path $distDir "TypelessService"
if (-not (Test-Path $bundleDir)) {
    throw "PyInstaller output missing: $bundleDir"
}

Get-ChildItem $bundleDir -Force | ForEach-Object {
    Move-Item -Path $_.FullName -Destination $distDir -Force
}
Remove-Item -Path $bundleDir -Recurse -Force

$exePath = Join-Path $distDir "TypelessService.exe"
if (-not (Test-Path $exePath)) {
    throw "Backend executable missing: $exePath"
}

Write-Host "Backend build complete: $exePath"
