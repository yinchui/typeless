$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceScript = Join-Path $repoRoot "desktop\hotkey_agent.ahk"
$distDir = Join-Path $repoRoot "dist\agent"
$outputExe = Join-Path $distDir "TypelessAgent.exe"
$outputScript = Join-Path $distDir "TypelessAgent.ahk"

function Resolve-AhkRuntimeExe {
    $candidates = @(
        (Join-Path $env:ProgramFiles "AutoHotkey\v2\AutoHotkey64.exe"),
        (Join-Path $env:ProgramFiles "AutoHotkey\AutoHotkey64.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "AutoHotkey\v2\AutoHotkey64.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "AutoHotkey\AutoHotkey64.exe"),
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

$ahkRuntime = Resolve-AhkRuntimeExe
Copy-Item -Path $ahkRuntime -Destination $outputExe -Force
Copy-Item -Path $sourceScript -Destination $outputScript -Force

if (-not (Test-Path $outputExe)) {
    throw "Agent executable missing after build: $outputExe"
}
if (-not (Test-Path $outputScript)) {
    throw "Agent script missing after build: $outputScript"
}

Write-Host "Agent build complete: $outputExe (+ TypelessAgent.ahk)"
