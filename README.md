# Voice Text Organizer (Windows MVP)

Background desktop tool for converting spoken language into clean, structured text.

## Core flow

1. Press `Alt + Space` once to start recording.
2. Press `Alt + Space` again to stop.
3. Service transcribes + rewrites automatically.
4. Hotkey agent inserts final text at cursor (or replaces selected text).

## Stack

- AutoHotkey v2 (`desktop/hotkey_agent.ahk`)
- FastAPI service (`service/src/voice_text_organizer`)
- Default cloud provider: SiliconFlow
- Optional local rewrite provider: Ollama

## Setup

1. Install Python dependencies:

```powershell
python -m pip install fastapi uvicorn pydantic "httpx>=0.27,<0.28" pytest sounddevice
```

2. Configure env vars (PowerShell example):

```powershell
$env:SILICONFLOW_API_KEY="your_new_key_here"
$env:VTO_DEFAULT_MODE="cloud"
```

3. Start service:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-dev.ps1
```

4. Start hotkey agent:

```powershell
AutoHotkey64.exe .\desktop\hotkey_agent.ahk
```

5. Open tray menu `Settings` to update API Key anytime (effective immediately).

## Troubleshooting (No text inserted)

1. Launch with `start-app.cmd` (recommended).
2. Check backend startup/runtime logs:
   - `service/runtime/backend.log`
   - `service/runtime/backend.stderr.log`
3. Check hotkey log: `service/runtime/hotkey.log` (Tray -> `Open Logs Folder`)
4. Verify `sounddevice` is installed in the same Python used by backend:

```powershell
python -m pip show sounddevice
```

5. If needed, force backend Python explicitly:

```powershell
$env:VTO_PYTHON_EXE="C:\Users\YourName\AppData\Local\Programs\Python\Python310\python.exe"
```

## One-Click Start

Double-click `start-app.cmd` in project root to launch both:
- FastAPI service
- AutoHotkey hotkey agent

`start-app.cmd` starts backend service in hidden mode, so you do not need to keep a black console window open.

Optional check mode:

```powershell
.\start-app.cmd --check
```

## Security note

- Never commit API keys.
- If a key is exposed, revoke and rotate it immediately.
