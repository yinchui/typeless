$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$serviceDir = Join-Path $repoRoot "service"
$runtimeDir = Join-Path $serviceDir "runtime"
$logPath = Join-Path $runtimeDir "backend.log"
$stdoutLogPath = Join-Path $runtimeDir "backend.stdout.log"
$stderrLogPath = Join-Path $runtimeDir "backend.stderr.log"

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

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

try {
    $python = Resolve-PythonCommand -RepoRoot $repoRoot
    $pythonExe = [string]$python.exe
    $prefixArgs = @($python.prefixArgs)

    $uvicornArgs = @(
        "-m", "uvicorn",
        "voice_text_organizer.main:app",
        "--app-dir", "src",
        "--host", "127.0.0.1",
        "--port", "8775"
    )

    $allArgs = @($prefixArgs + $uvicornArgs)
    $startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    @(
        "[$startedAt] starting backend with: $pythonExe $($allArgs -join ' ')",
        "[$startedAt] stdout log: $stdoutLogPath",
        "[$startedAt] stderr log: $stderrLogPath"
    ) | Out-File -FilePath $logPath -Encoding utf8

    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList $allArgs `
        -WorkingDirectory $serviceDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLogPath `
        -RedirectStandardError $stderrLogPath `
        -PassThru

    $process.WaitForExit()
    $exitCode = $process.ExitCode
    $stoppedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$stoppedAt] backend exited with code: $exitCode" | Out-File -FilePath $logPath -Encoding utf8 -Append
    exit $exitCode
}
catch {
    $failedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$failedAt] backend startup failed: $($_.Exception.Message)" | Out-File -FilePath $logPath -Encoding utf8 -Append
    throw
}
