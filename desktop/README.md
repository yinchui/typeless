# Hotkey Agent (Windows)

## What it does

- Runs in background.
- Provides a desktop dashboard UI (Home + Dictionary) based on the new design.
- Press `Alt + Space` once to start recording.
- Press `Alt + Space` again to stop recording and trigger voice-to-text + rewrite.
- While recording, a bottom mini voice bar is shown (wave animation only).
- While recording, system playback is paused temporarily and resumed after stop.
- Inserts final text into current cursor (or replaces selected text).
- Tray menu includes `Open Dashboard`, `Settings`, and `Open Logs Folder`.

## Requirements

- AutoHotkey v2
- Python service running at `http://127.0.0.1:8775`

## Run

```powershell
AutoHotkey64.exe .\desktop\hotkey_agent.ahk
```

## Config

Runtime settings:
- Click tray icon once (or right click) -> `Open Dashboard` to open the main UI.
- Right click tray icon -> `Settings`
- Save API Key and default mode (`cloud` / `local`) instantly
- Right click tray icon -> `Open Logs Folder` to inspect runtime logs

Static constants at top of `desktop/hotkey_agent.ahk`:
- `baseUrl`
- hotkey: `!Space` (Alt + Space)

Runtime directory:
- default: `%LOCALAPPDATA%\Typeless\runtime`
- override with env var `VTO_RUNTIME_DIR`

Update check:
- Hotkey agent checks `GET /v1/app/version` on startup and when opening dashboard.
- When update is available, dashboard home shows a clickable "发现新版本 vX.Y.Z" entry.
