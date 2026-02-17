@echo off
setlocal EnableExtensions

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "RUNTIME_DIR=%ROOT_DIR%\runtime"
set "VTO_RUNTIME_DIR=%RUNTIME_DIR%"
if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%" >nul 2>nul

set "RUN_SERVICE_PS1=%ROOT_DIR%\scripts\run-service.ps1"
set "HOTKEY_AHK=%ROOT_DIR%\desktop\hotkey_agent.ahk"
set "AHK_EXE="

for %%P in (
    "%ProgramFiles%\AutoHotkey\v2\AutoHotkey64.exe"
    "%ProgramFiles%\AutoHotkey\AutoHotkey64.exe"
    "%LocalAppData%\Programs\AutoHotkey\v2\AutoHotkey64.exe"
    "%LocalAppData%\Programs\AutoHotkey\AutoHotkey64.exe"
) do (
    if not defined AHK_EXE if exist "%%~P" set "AHK_EXE=%%~P"
)

if not defined AHK_EXE (
    for /f "delims=" %%I in ('where AutoHotkey64.exe 2^>nul') do (
        if not defined AHK_EXE set "AHK_EXE=%%~I"
    )
)

if /i "%~1"=="--check" goto :check

if not exist "%RUN_SERVICE_PS1%" (
    echo [ERROR] Missing file: %RUN_SERVICE_PS1%
    exit /b 1
)
if not exist "%HOTKEY_AHK%" (
    echo [ERROR] Missing file: %HOTKEY_AHK%
    exit /b 1
)
if not defined AHK_EXE (
    echo [ERROR] AutoHotkey64.exe not found.
    echo Install AutoHotkey v2 and run again.
    exit /b 1
)

call :stop_conflicting_typeless_backend

call :probe_health
if not "%SERVICE_UP%"=="200" (
    start "Voice Text Organizer Service" powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%RUN_SERVICE_PS1%"
    for /l %%I in (1,1,10) do (
        timeout /t 1 /nobreak >nul
        call :probe_health
        if "%SERVICE_UP%"=="200" goto :service_ready
    )
)
:service_ready
start "Voice Text Organizer Hotkey Agent" "%AHK_EXE%" "%HOTKEY_AHK%"

call :probe_health
if "%SERVICE_UP%"=="200" (
    echo [OK] Voice Text Organizer started.
) else (
    echo [WARN] Hotkey agent started, but backend health check failed on 127.0.0.1:8775.
)
echo - Service script: %RUN_SERVICE_PS1%
echo - Hotkey script: %HOTKEY_AHK%
echo - Runtime dir: %VTO_RUNTIME_DIR%
exit /b 0

:stop_conflicting_typeless_backend
set "PORT_OWNER="
set "PORT_OWNER_PID="
set "PORT_OWNER_NAME="
set "PORT_OWNER_PATH="
for /f "usebackq delims=" %%L in (`powershell -NoProfile -Command "$conn = Get-NetTCPConnection -LocalPort 8775 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if($conn){ $proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $conn.OwningProcess); if($proc){ Write-Output ($proc.ProcessId.ToString() + '|' + $proc.Name + '|' + $proc.ExecutablePath) } }"`) do set "PORT_OWNER=%%L"
if not defined PORT_OWNER exit /b 0

for /f "tokens=1-3 delims=|" %%A in ("%PORT_OWNER%") do (
    set "PORT_OWNER_PID=%%~A"
    set "PORT_OWNER_NAME=%%~B"
    set "PORT_OWNER_PATH=%%~C"
)

if /i "%PORT_OWNER_NAME%"=="TypelessService.exe" (
    echo [INFO] Stopping existing Typeless backend on port 8775: %PORT_OWNER_PATH%
    taskkill /PID %PORT_OWNER_PID% /F >nul 2>nul
    timeout /t 1 /nobreak >nul
)
exit /b 0

:probe_health
set "SERVICE_UP=0"
for /f "delims=" %%S in ('powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; try { (Invoke-WebRequest -UseBasicParsing -Uri ''http://127.0.0.1:8775/health'' -TimeoutSec 1).StatusCode } catch { 0 }"') do set "SERVICE_UP=%%S"
exit /b 0

:check
set "ERR=0"
if exist "%RUN_SERVICE_PS1%" (
    echo [OK] Found: %RUN_SERVICE_PS1%
) else (
    echo [ERROR] Missing: %RUN_SERVICE_PS1%
    set "ERR=1"
)
if exist "%HOTKEY_AHK%" (
    echo [OK] Found: %HOTKEY_AHK%
) else (
    echo [ERROR] Missing: %HOTKEY_AHK%
    set "ERR=1"
)
if defined AHK_EXE (
    echo [OK] AutoHotkey: %AHK_EXE%
) else (
    echo [ERROR] AutoHotkey64.exe not found.
    set "ERR=1"
)
if "%ERR%"=="0" (
    echo [OK] One-click launcher is ready.
    echo [OK] Runtime dir: %VTO_RUNTIME_DIR%
) else (
    echo [ERROR] One-click launcher prerequisites not met.
)
exit /b %ERR%
