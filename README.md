# 语音文字整理器 (Windows MVP)

后台桌面工具，将口语转换为清晰、结构化的文本。

## 核心流程

1. 按一次 `Alt + Space` 开始录音。
2. 再次按 `Alt + Space` 停止。
3. 录音时会出现底部迷你语音条（仅波浪动画，无文字）。
4. 服务自动转录并重写。
5. 热键代理在光标处插入最终文本（或替换选中文本）。

## 技术栈

- AutoHotkey v2 (`desktop/hotkey_agent.ahk`)
- FastAPI 服务 (`service/src/voice_text_organizer`)
- 默认云服务提供商：SiliconFlow
- 可选本地重写服务提供商：Ollama
- 发布打包：PyInstaller + Ahk2Exe + Inno Setup

## 安装步骤

1. 安装 Python 依赖：

```powershell
python -m pip install fastapi uvicorn pydantic "httpx>=0.27,<0.28" pytest sounddevice
```

2. 配置环境变量（PowerShell 示例）：

```powershell
$env:SILICONFLOW_API_KEY="your_new_key_here"
$env:VTO_DEFAULT_MODE="cloud"
```

3. 启动服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-dev.ps1
```

4. 启动热键代理：

```powershell
AutoHotkey64.exe .\desktop\hotkey_agent.ahk
```

5. 打开托盘菜单 `Settings` 随时更新 API Key（立即生效）。

## 运行时目录

默认运行时目录：
- `%LOCALAPPDATA%\Typeless\runtime`

可选覆盖：
- 设置环境变量 `VTO_RUNTIME_DIR` 指向自定义目录。

运行时文件包括：
- `settings.json`
- `history.db`
- `backend.log` / `backend.stdout.log` / `backend.stderr.log`
- `hotkey.log`

## 故障排除（无文本插入）

1. 使用 `start-app.cmd` 启动（推荐）。
2. 检查后端启动/运行日志：
   - `%LOCALAPPDATA%\Typeless\runtime\backend.log`
   - `%LOCALAPPDATA%\Typeless\runtime\backend.stderr.log`
3. 检查热键日志：`%LOCALAPPDATA%\Typeless\runtime\hotkey.log`（托盘 → `Open Logs Folder`）
4. 验证 `sounddevice` 已安装在与后端相同的 Python 环境中：

```powershell
python -m pip show sounddevice
```

5. 如需要，可显式指定后端 Python：

```powershell
$env:VTO_PYTHON_EXE="C:\Users\YourName\AppData\Local\Programs\Python\Python310\python.exe"
```

## 一键启动

双击项目根目录下的 `start-app.cmd` 启动以下两项：
- FastAPI 服务
- AutoHotkey 热键代理

`start-app.cmd` 以后台模式启动后端服务，因此无需保持黑色控制台窗口打开。

可选检查模式：

```powershell
.\start-app.cmd --check
```

## 构建发布（Windows x64）

1. 构建后端 EXE：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-backend.ps1
```

2. 构建热键代理 EXE：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-agent.ps1
```

3. 构建安装包（Inno Setup）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-installer.ps1
```

构建产物：
- `dist/backend/TypelessService.exe`（含 `_internal` 依赖目录）
- `dist/agent/TypelessAgent.exe`
- `dist/installer/Typeless-Setup-x64-v*.exe`
- `dist/installer/SHA256SUMS.txt`

GitHub Release：
- 打 tag `vX.Y.Z` 会触发 `.github/workflows/release.yml` 自动构建并上传安装包。

版本检查接口：
- `GET /v1/app/version`

## 安全注意事项

- 切勿提交 API 密钥。
- 如果密钥泄露，请立即撤销并更换。
- 当前内测版未做代码签名，首次安装可能出现 SmartScreen 提示。

## Transcription-First Behavior (v0.1.8+)

The backend now enforces a transcription-first policy:

- If there is no selected text, output is always the spoken transcription.
- If there is selected text, only translation whitelist commands trigger rewrite.
- Non-whitelist commands with selected text return spoken transcription text.

Translation whitelist (v1):

- `翻译成中文` / `翻成中文` / `译成中文` / `英译中`
- `翻译成英文` / `翻成英文` / `译成英文` / `中译英`
- `translate to chinese` / `translate to english`

If whitelist rewrite fails, the service falls back to transcription output.
