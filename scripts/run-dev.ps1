$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$serviceDir = Join-Path $repoRoot "service"

if (-not $env:VTO_RUNTIME_DIR) {
    if ($env:LOCALAPPDATA) {
        $env:VTO_RUNTIME_DIR = Join-Path $env:LOCALAPPDATA "Typeless\runtime"
    } else {
        $env:VTO_RUNTIME_DIR = Join-Path $repoRoot "service\runtime"
    }
}

function Resolve-PythonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    if ($env:VTO_PYTHON_EXE -and (Test-Path $env:VTO_PYTHON_EXE)) {
        return @{
            exe = (Resolve-Path $env:VTO_PYTHON_EXE).Path
            prefixArgs = @()
        }
    }

    $venvCandidates = @(
        (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
        (Join-Path $RepoRoot "service\.venv\Scripts\python.exe")
    )
    foreach ($candidate in $venvCandidates) {
        if (Test-Path $candidate) {
            return @{
                exe = (Resolve-Path $candidate).Path
                prefixArgs = @()
            }
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return @{
            exe = $pythonCmd.Source
            prefixArgs = @()
        }
    }

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        return @{
            exe = $pyCmd.Source
            prefixArgs = @("-3")
        }
    }

    throw "Python runtime not found. Install Python or set VTO_PYTHON_EXE."
}

$python = Resolve-PythonCommand -RepoRoot $repoRoot
$pythonExe = [string]$python.exe
$prefixArgs = @($python.prefixArgs)
$allArgs = @(
    $prefixArgs +
    @(
        "-m", "uvicorn",
        "voice_text_organizer.main:app",
        "--app-dir", "src",
        "--host", "127.0.0.1",
        "--port", "8775",
        "--reload"
    )
)

Set-Location $serviceDir
$oldPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $pythonExe @allArgs
$ErrorActionPreference = $oldPreference
