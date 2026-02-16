$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceScript = Join-Path $repoRoot "desktop\hotkey_agent.ahk"
$distDir = Join-Path $repoRoot "dist\agent"
$outputExe = Join-Path $distDir "TypelessAgent.exe"

function Get-Ahk2ExeCandidates {
    return @(
        (Join-Path $env:ProgramFiles "AutoHotkey\Compiler\Ahk2Exe.exe"),
        (Join-Path $env:ProgramFiles "AutoHotkey\v2\Compiler\Ahk2Exe.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "AutoHotkey\Compiler\Ahk2Exe.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "AutoHotkey\v2\Compiler\Ahk2Exe.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\AutoHotkey\Compiler\Ahk2Exe.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\AutoHotkey\v2\Compiler\Ahk2Exe.exe")
    )
}

function Resolve-AhkBaseExe {
    $candidates = @(
        (Join-Path $env:ProgramFiles "AutoHotkey\v2\AutoHotkey64.exe"),
        (Join-Path $env:ProgramFiles "AutoHotkey\AutoHotkey64.exe"),
        (Join-Path $env:ProgramFiles "AutoHotkey\v2\AutoHotkey.exe"),
        (Join-Path $env:ProgramFiles "AutoHotkey\AutoHotkey.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "AutoHotkey\v2\AutoHotkey64.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "AutoHotkey\AutoHotkey64.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "AutoHotkey\v2\AutoHotkey.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "AutoHotkey\AutoHotkey.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\AutoHotkey\v2\AutoHotkey64.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\AutoHotkey\AutoHotkey64.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\AutoHotkey\v2\AutoHotkey.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\AutoHotkey\AutoHotkey.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    throw "AutoHotkey64.exe not found. Install AutoHotkey v2 first."
}

function Resolve-AhkInstallerScript {
    $candidates = @(
        (Join-Path $env:ProgramFiles "AutoHotkey\UX\install-ahk2exe.ahk"),
        (Join-Path $env:ProgramFiles "AutoHotkey\v2\UX\install-ahk2exe.ahk"),
        (Join-Path ${env:ProgramFiles(x86)} "AutoHotkey\UX\install-ahk2exe.ahk"),
        (Join-Path ${env:ProgramFiles(x86)} "AutoHotkey\v2\UX\install-ahk2exe.ahk"),
        (Join-Path $env:LOCALAPPDATA "Programs\AutoHotkey\UX\install-ahk2exe.ahk"),
        (Join-Path $env:LOCALAPPDATA "Programs\AutoHotkey\v2\UX\install-ahk2exe.ahk")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return $null
}

function Download-Ahk2ExeBundle {
    param([string]$RootDir)

    $toolsRoot = Join-Path $RootDir "dist\tools\ahk2exe"
    $bundleDir = Join-Path $toolsRoot "bundle"
    $zipPath = Join-Path $toolsRoot "Ahk2Exe.zip"

    New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null

    $headers = @{ "User-Agent" = "typeless-build-agent" }
    $downloadUrl = "https://github.com/AutoHotkey/Ahk2Exe/releases/latest/download/Ahk2Exe.zip"
    Invoke-WebRequest -Uri $downloadUrl -Headers $headers -OutFile $zipPath

    if (Test-Path $bundleDir) {
        Remove-Item -Recurse -Force $bundleDir
    }
    Expand-Archive -Path $zipPath -DestinationPath $bundleDir -Force

    $exe = Get-ChildItem -Path $bundleDir -Filter "Ahk2Exe.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $exe) {
        throw "Downloaded Ahk2Exe bundle does not contain Ahk2Exe.exe"
    }
    return $exe.FullName
}

function Resolve-Ahk2Exe {
    $candidates = Get-Ahk2ExeCandidates

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $cmd = Get-Command Ahk2Exe.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $installerScript = Resolve-AhkInstallerScript
    if ($installerScript) {
        $ahkBase = Resolve-AhkBaseExe
        Write-Host "Ahk2Exe not found. Installing compiler from: $installerScript"
        & $ahkBase $installerScript /silent

        foreach ($candidate in $candidates) {
            if (Test-Path $candidate) {
                return $candidate
            }
        }

        $cmd = Get-Command Ahk2Exe.exe -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }

    Write-Host "Ahk2Exe not found in system paths. Downloading standalone Ahk2Exe bundle..."
    return Download-Ahk2ExeBundle -RootDir $repoRoot
}

if (-not (Test-Path $sourceScript)) {
    throw "Source AHK script not found: $sourceScript"
}

New-Item -ItemType Directory -Force -Path $distDir | Out-Null

$ahk2exe = Resolve-Ahk2Exe
$ahkBase = Resolve-AhkBaseExe

$nativeExitHandling = Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue
if ($nativeExitHandling) {
    $previousNativeExitHandling = $PSNativeCommandUseErrorActionPreference
    $PSNativeCommandUseErrorActionPreference = $false
}

try {
    & $ahk2exe /in $sourceScript /out $outputExe /base $ahkBase
    $ahkExitCode = $LASTEXITCODE
}
finally {
    if ($nativeExitHandling) {
        $PSNativeCommandUseErrorActionPreference = $previousNativeExitHandling
    }
}

if (-not (Test-Path $outputExe)) {
    throw "Agent executable missing after build: $outputExe (Ahk2Exe exit code: $ahkExitCode)"
}

if ($ahkExitCode -ne 0) {
    Write-Warning "Ahk2Exe exited with code $ahkExitCode, but output executable exists and will be used."
}

Write-Host "Agent build complete: $outputExe"
