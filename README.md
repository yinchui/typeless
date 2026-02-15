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

## 故障排除（无文本插入）

1. 使用 `start-app.cmd` 启动（推荐）。
2. 检查后端启动/运行日志：
   - `service/runtime/backend.log`
   - `service/runtime/backend.stderr.log`
3. 检查热键日志：`service/runtime/hotkey.log`（托盘 → `Open Logs Folder`）
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

## 安全注意事项

- 切勿提交 API 密钥。
- 如果密钥泄露，请立即撤销并更换。
