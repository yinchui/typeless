param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$innoScript = Join-Path $repoRoot "packaging\inno\Typeless.iss"
$installerOutDir = Join-Path $repoRoot "dist\installer"
$backendExe = Join-Path $repoRoot "dist\backend\TypelessService.exe"
$agentExe = Join-Path $repoRoot "dist\agent\TypelessAgent.exe"

function Resolve-Iscc {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    throw "ISCC.exe not found. Install Inno Setup 6 first."
}

function Resolve-VersionFromPyproject {
    $pyproject = Join-Path $repoRoot "service\pyproject.toml"
    if (-not (Test-Path $pyproject)) {
        throw "pyproject.toml not found: $pyproject"
    }
    $raw = Get-Content $pyproject -Raw -Encoding UTF8
    $match = [Regex]::Match($raw, '(?m)^\s*version\s*=\s*"([^"]+)"\s*$')
    if (-not $match.Success) {
        throw "Could not read project version from pyproject.toml"
    }
    return $match.Groups[1].Value
}

if (-not (Test-Path $backendExe)) {
    throw "Backend build artifact missing: $backendExe"
}
if (-not (Test-Path $agentExe)) {
    throw "Agent build artifact missing: $agentExe"
}
if (-not (Test-Path $innoScript)) {
    throw "Inno script missing: $innoScript"
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = Resolve-VersionFromPyproject
}
$Version = $Version.Trim().TrimStart("v", "V")

New-Item -ItemType Directory -Force -Path $installerOutDir | Out-Null

$iscc = Resolve-Iscc
& $iscc `
    "/DAppVersion=$Version" `
    "/DRepoRoot=$repoRoot" `
    "/DOutputDir=$installerOutDir" `
    $innoScript

$shaFile = Join-Path $installerOutDir "SHA256SUMS.txt"
Get-ChildItem -Path $installerOutDir -Filter "*.exe" | ForEach-Object {
    $hash = Get-FileHash -Path $_.FullName -Algorithm SHA256
    "{0} *{1}" -f $hash.Hash.ToLowerInvariant(), $_.Name
} | Set-Content -Path $shaFile -Encoding UTF8

Write-Host "Installer build complete. Output: $installerOutDir"
