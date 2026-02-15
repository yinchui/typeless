# Hotkey Agent (Windows)

## What it does

- Runs in background.
- Press `Alt + Space` once to start recording.
- Press `Alt + Space` again to stop recording and trigger voice-to-text + rewrite.
- Inserts final text into current cursor (or replaces selected text).
- Tray menu includes `Settings`, where you can update API Key and default mode at any time.

## Requirements

- AutoHotkey v2
- Python service running at `http://127.0.0.1:8775`

## Run

```powershell
AutoHotkey64.exe .\desktop\hotkey_agent.ahk
```

## Config

Runtime settings:
- Right click tray icon -> `Settings`
- Save API Key and default mode (`cloud` / `local`) instantly
- Right click tray icon -> `Open Logs Folder` to inspect runtime logs

Static constants at top of `desktop/hotkey_agent.ahk`:
- `baseUrl`
- hotkey: `!Space` (Alt + Space)
