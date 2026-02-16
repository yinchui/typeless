$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceScript = Join-Path $repoRoot "desktop\hotkey_agent.ahk"
$distDir = Join-Path $repoRoot "dist\agent"
$outputExe = Join-Path $distDir "TypelessAgent.exe"

function Resolve-Ahk2Exe {
    $candidates = @(
        (Join-Path $env:ProgramFiles "AutoHotkey\Compiler\Ahk2Exe.exe"),
        (Join-Path $env:ProgramFiles "AutoHotkey\v2\Compiler\Ahk2Exe.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\AutoHotkey\Compiler\Ahk2Exe.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\AutoHotkey\v2\Compiler\Ahk2Exe.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $cmd = Get-Command Ahk2Exe.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    throw "Ahk2Exe.exe not found. Install AutoHotkey v2 compiler first."
}

function Resolve-AhkBaseExe {
    $candidates = @(
        (Join-Path $env:ProgramFiles "AutoHotkey\v2\AutoHotkey64.exe"),
        (Join-Path $env:ProgramFiles "AutoHotkey\AutoHotkey64.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\AutoHotkey\v2\AutoHotkey64.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\AutoHotkey\AutoHotkey64.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    throw "AutoHotkey64.exe not found. Install AutoHotkey v2 first."
}

if (-not (Test-Path $sourceScript)) {
    throw "Source AHK script not found: $sourceScript"
}

New-Item -ItemType Directory -Force -Path $distDir | Out-Null

$ahk2exe = Resolve-Ahk2Exe
$ahkBase = Resolve-AhkBaseExe

& $ahk2exe /in $sourceScript /out $outputExe /base $ahkBase

if (-not (Test-Path $outputExe)) {
    throw "Agent executable missing after build: $outputExe"
}

Write-Host "Agent build complete: $outputExe"
