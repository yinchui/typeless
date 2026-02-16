# 修复文字覆盖 + 上下文续写 + 提速提质 实现计划

> **For Claude:** 必需子技能：使用 superpowers:executing-plans 逐任务实施此计划。

**目标：** 修复三个问题：(1) 录音后原有文字被覆盖 (2) 续写时缺乏上下文理解 (3) 改写速度和质量不够好。

**架构：** AHK 端修复焦点抢占和文字获取逻辑；Python 后端增加 `existing_text` 上下文传递，重构 prompt 为 messages 格式并支持续写/选中/独立三种模式，升级默认 LLM 为 DeepSeek-V3。

**技术栈：** AutoHotkey v2, Python 3.10+, FastAPI, Pydantic v2, httpx, pytest, pytest-mock.

---

## 执行期间应用的技能

- `@test-driven-development` 用于每个 Python 步骤。
- `@systematic-debugging` 如果任何测试或集成行为失败。
- `@verification-before-completion` 在声称完成之前。

---

### 任务 1: 修复波形 GUI 焦点抢占

**文件：**
- 修改：`desktop/hotkey_agent.ahk:219`（InitWaveformGui）

**步骤 1: 修改波形 GUI 创建以防止焦点抢占**

在 `InitWaveformGui()`，第 219 行，将：
```ahk
waveformGui := Gui("-Caption +ToolWindow +AlwaysOnTop +E0x20")
```
改为：
```ahk
waveformGui := Gui("-Caption +ToolWindow +AlwaysOnTop +E0x20 +E0x08000000")
```

`E0x08000000` 是 `WS_EX_NOACTIVATE` — 防止窗口成为前台窗口并抢占焦点。

**步骤 2: 验证波形仍使用 `NA` 标志显示**

确认 `ShowWaveformIndicator()` 在第 247 行已在 `waveformGui.Show()` 中使用 `"NA"` 选项。`NA` 表示显示时"不激活"。`+E0x08000000` 即使在点击或其他事件上也增加了操作系统级别的保证。

第 247 行已有：`waveformGui.Show("NA x" . x . " y" . y)` — 确认无误。

**步骤 3: 提交**

```bash
git add desktop/hotkey_agent.ahk
git commit -m "fix: prevent waveform GUI from stealing focus (WS_EX_NOACTIVATE)"
```

---

### 任务 2: 修复 InsertText 保留现有文字

**文件：**
- 修改：`desktop/hotkey_agent.ahk:894-951`（InsertText）

**步骤 1: 在粘贴前添加取消选择安全处理**

在 `InsertText()`，第 905 行的 `Sleep(80)` 之后，第 907 行的剪贴板粘贴逻辑之前，添加：

```ahk
    ; 取消选择任何自动选中的文字，防止覆盖现有内容。
    Send("{End}")
    Sleep(50)
```

更新后的完整部分（第 904-907 行）：
```ahk
    ; 给前台应用一个短暂的时间在热键释放后重新获得焦点。
    Sleep(80)

    ; 取消选择任何自动选中的文字，防止覆盖现有内容。
    Send("{End}")
    Sleep(50)

    clipSaved := ClipboardAll()
```

**步骤 2: 提交**

```bash
git add desktop/hotkey_agent.ahk
git commit -m "fix: deselect text before paste to prevent overwriting existing content"
```

---

### 任务 3: 在 AHK 中添加 GetFullTextSafe 函数

**文件：**
- 修改：`desktop/hotkey_agent.ahk`（在 `GetSelectedTextSafe` 之后，约第 892 行）

**步骤 1: 添加 GetFullTextSafe 函数**

在 `GetSelectedTextSafe()` 之后（第 892 行之后）插入：

```ahk
GetFullTextSafe()
{
    clipSaved := ClipboardAll()
    fullText := ""
    try
    {
        A_Clipboard := ""
        Send("^a")
        Sleep(50)
        Send("^c")
        if (ClipWait(0.3))
            fullText := A_Clipboard
        ; 取消选择并将光标移到末尾
        Send("{End}")
    }
    finally
    {
        A_Clipboard := clipSaved
    }
    return fullText
}
```

**步骤 2: 提交**

```bash
git add desktop/hotkey_agent.ahk
git commit -m "feat: add GetFullTextSafe to capture all text in input field"
```

---

### 任务 4: 修改 StartRecordingSession 以捕获现有文字

**文件：**
- 修改：`desktop/hotkey_agent.ahk:100-130`（StartRecordingSession）
- 修改：`desktop/hotkey_agent.ahk:953-958`（ApiStartRecord）

**步骤 1: 更新 StartRecordingSession 以捕获现有文字**

替换第 105-108 行：
```ahk
        PausePlaybackForRecording()
        targetWindowId := WinExist("A")
        selectedText := GetSelectedTextSafe()
        sessionId := ApiStartRecord(selectedText)
```

改为：
```ahk
        PausePlaybackForRecording()
        targetWindowId := WinExist("A")
        selectedText := GetSelectedTextSafe()
        existingText := ""
        if (selectedText = "")
            existingText := GetFullTextSafe()
        sessionId := ApiStartRecord(selectedText, existingText)
```

**步骤 2: 更新 ApiStartRecord 以发送 existing_text**

替换第 953-958 行：
```ahk
ApiStartRecord(selectedText)
{
    q := Chr(34)
    payload := "{" . q . "selected_text" . q . ":" . q . JsonEscape(selectedText) . q . "}"
    response := HttpPost("/v1/record/start", payload)
    return ExtractJsonString(response, "session_id")
}
```

改为：
```ahk
ApiStartRecord(selectedText, existingText := "")
{
    q := Chr(34)
    payload := "{" . q . "selected_text" . q . ":" . q . JsonEscape(selectedText) . q
    payload .= "," . q . "existing_text" . q . ":" . q . JsonEscape(existingText) . q . "}"
    response := HttpPost("/v1/record/start", payload)
    return ExtractJsonString(response, "session_id")
}
```

**步骤 3: 提交**

```bash
git add desktop/hotkey_agent.ahk
git commit -m "feat: capture existing text and send to backend for context-aware rewriting"
```

---

### 任务 5: 在 schemas 和 session store 中添加 existing_text

**文件：**
- 修改：`service/src/voice_text_organizer/schemas.py:8-9`
- 修改：`service/src/voice_text_organizer/session_store.py:8-11,19`
- 测试：`service/tests/test_session_store.py`

**步骤 1: 编写失败的测试**

在 `service/tests/test_session_store.py` 中添加测试：

```python
def test_create_session_with_existing_text():
    store = SessionStore()
    sid = store.create(selected_text=None, existing_text="Hello world")
    session = store.get(sid)
    assert session.existing_text == "Hello world"
    assert session.selected_text is None


def test_create_session_existing_text_defaults_none():
    store = SessionStore()
    sid = store.create()
    session = store.get(sid)
    assert session.existing_text is None
```

**步骤 2: 运行测试验证失败**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_session_store.py -v -k "existing_text"`
预期：FAIL — `create()` 不接受 `existing_text` 参数。

**步骤 3: 更新 schemas.py**

在 `service/src/voice_text_organizer/schemas.py` 中，修改 `StartSessionRequest`（第 8-9 行）：
```python
class StartSessionRequest(BaseModel):
    selected_text: str | None = None
    existing_text: str | None = None
```

**步骤 4: 更新 session_store.py**

在 `service/src/voice_text_organizer/session_store.py` 中：

更新 `Session` 数据类（第 8-11 行）：
```python
@dataclass
class Session:
    session_id: str
    selected_text: str | None = None
    existing_text: str | None = None
```

更新 `create` 方法（第 19 行）：
```python
    def create(self, selected_text: str | None = None, existing_text: str | None = None) -> str:
        session_id = str(uuid4())
        with self._lock:
            self._data[session_id] = Session(
                session_id=session_id,
                selected_text=selected_text,
                existing_text=existing_text,
            )
        return session_id
```

**步骤 5: 运行测试验证通过**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_session_store.py -v`
预期：全部通过

**步骤 6: 提交**

```bash
git add service/src/voice_text_organizer/schemas.py service/src/voice_text_organizer/session_store.py service/tests/test_session_store.py
git commit -m "feat: add existing_text field to session schema and store"
```

---

### 任务 6: 重构 build_prompt 返回 messages 列表并支持三种模式

**文件：**
- 修改：`service/src/voice_text_organizer/rewrite.py`
- 测试：`service/tests/test_rewrite.py`

**步骤 1: 编写失败的测试**

在 `service/tests/test_rewrite.py` 中添加/替换测试：

```python
from voice_text_organizer.rewrite import build_prompt, postprocess_rewrite_output


def test_build_prompt_standalone_mode():
    """无上下文 — 独立改写。"""
    messages = build_prompt("今天天气真不错我想出去走走")
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "今天天气真不错" in messages[1]["content"]
    # 不应提及已有文字或选中文字
    assert "已有文字" not in messages[1]["content"]
    assert "existing" not in messages[1]["content"].lower()


def test_build_prompt_selected_text_mode():
    """选中文字 — 精炼/替换模式。"""
    messages = build_prompt("把这段改成更正式的", selected_text="嗨大家好")
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "嗨大家好" in messages[1]["content"]
    assert "把这段改成更正式的" in messages[1]["content"]


def test_build_prompt_continuation_mode():
    """有 existing_text 但无 selected_text — 续写模式。"""
    messages = build_prompt(
        "然后我们去吃午饭",
        existing_text="今天上午开了个会",
    )
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "今天上午开了个会" in messages[1]["content"]
    assert "然后我们去吃午饭" in messages[1]["content"]


def test_build_prompt_continuation_truncates_long_context():
    """existing_text 超过 2000 字符时截断为最后 2000。"""
    long_text = "这是很长的文字。" * 500  # 4000 chars
    messages = build_prompt("继续写", existing_text=long_text)
    user_content = messages[1]["content"]
    # 提示中的已有文字应该被截断
    assert len(long_text) > 2000
    # 无法检查精确字符数，因为嵌入在提示中，
    # 但完整的 4000 字符字符串不应原样出现
    assert long_text not in user_content


def test_build_prompt_selected_text_takes_priority_over_existing():
    """当同时提供 selected_text 和 existing_text 时，使用 selected_text 模式。"""
    messages = build_prompt(
        "改成英文",
        selected_text="你好世界",
        existing_text="前面的内容",
    )
    user_content = messages[1]["content"]
    assert "你好世界" in user_content
    # 当 selected_text 存在时，existing_text 被忽略
    assert "前面的内容" not in user_content
```

**步骤 2: 运行测试验证失败**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_rewrite.py -v -k "build_prompt"`
预期：FAIL — `build_prompt` 返回 `str` 而不是 `list`。

**步骤 3: 重写 build_prompt 并简化 rewrite.py**

替换 `service/src/voice_text_organizer/rewrite.py` 中的整个 `build_prompt` 函数并更新 `SYSTEM_RULES`：

```python
SYSTEM_RULES = (
    "You are a language organizer. "
    "Rewrite spoken input into clear, structured text. "
    "Remove filler words and redundancy, preserve intent and details, "
    "and do not add facts. "
    "Keep the same language as the input. "
    "Use real line breaks for paragraph separation. "
    "Use bullet points when listing multiple items or steps."
)

MAX_EXISTING_TEXT_CHARS = 2000


def _truncate_existing_text(text: str) -> str:
    if len(text) <= MAX_EXISTING_TEXT_CHARS:
        return text
    return "..." + text[-MAX_EXISTING_TEXT_CHARS:]


def build_prompt(
    voice_text: str,
    selected_text: str | None = None,
    existing_text: str | None = None,
) -> list[dict[str, str]]:
    system_msg = {"role": "system", "content": SYSTEM_RULES}

    if selected_text:
        user_content = (
            f"Selected text to refine:\n{selected_text}\n\n"
            f"Voice instruction:\n{voice_text}\n\n"
            "Rewrite the selected text according to the voice instruction. "
            "Return only the rewritten text."
        )
    elif existing_text:
        truncated = _truncate_existing_text(existing_text)
        user_content = (
            f"The user has already written:\n---\n{truncated}\n---\n\n"
            f"The user then spoke to continue:\n{voice_text}\n\n"
            "Output ONLY the new continuation text. "
            "Do NOT repeat the existing text. "
            "The continuation must flow naturally from the existing text in style and tone. "
            "Remove filler words and organize the spoken content clearly."
        )
    else:
        user_content = (
            f"Voice text:\n{voice_text}\n\n"
            "Organize this spoken text into clear, structured written text. "
            "Return only the final organized text."
        )

    return [system_msg, {"role": "user", "content": user_content}]
```

**步骤 4: 运行测试验证通过**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_rewrite.py -v -k "build_prompt"`
预期：全部通过

**步骤 5: 提交**

```bash
git add service/src/voice_text_organizer/rewrite.py service/tests/test_rewrite.py
git commit -m "feat: refactor build_prompt to messages list with standalone/selected/continuation modes"
```

---

### 任务 7: 更新 providers 以接受 messages 列表

**文件：**
- 修改：`service/src/voice_text_organizer/providers/siliconflow.py`
- 修改：`service/src/voice_text_organizer/providers/ollama.py`
- 测试：`service/tests/test_siliconflow.py`
- 测试：`service/tests/test_ollama.py`

**步骤 1: 编写失败的测试**

在 `service/tests/test_siliconflow.py` 中更新 siliconflow 的测试 — 找到现有测试并更新 mock 调用以传递 messages 列表而不是字符串。添加如下测试：

```python
def test_rewrite_sends_messages_list(mock_httpx_post):
    """Provider 应直接转发 messages 列表。"""
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "Test input"},
    ]
    result = rewrite_with_siliconflow(messages, settings=settings)
    call_json = mock_httpx_post.call_args.kwargs["json"]
    assert call_json["messages"] == messages
```

同样在 `service/tests/test_ollama.py` 中为 ollama 添加：

```python
def test_rewrite_sends_messages_to_chat_api(mock_httpx_post):
    """Provider 应使用 /api/chat 并转发 messages 列表。"""
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "Test input"},
    ]
    result = rewrite_with_ollama(messages, settings=settings)
    call_args = mock_httpx_post.call_args
    assert "/api/chat" in call_args.args[0]
    call_json = call_args.kwargs["json"]
    assert call_json["messages"] == messages
```

**步骤 2: 运行测试验证失败**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_siliconflow.py tests/test_ollama.py -v -k "messages"`
预期：FAIL — providers 仍期望 `str` 参数。

**步骤 3: 更新 siliconflow.py**

替换 `service/src/voice_text_organizer/providers/siliconflow.py`：

```python
from __future__ import annotations

import httpx

from voice_text_organizer.config import Settings


def rewrite_with_siliconflow(messages: list[dict[str, str]], settings: Settings) -> str:
    if not settings.siliconflow_api_key:
        raise ValueError("Missing SILICONFLOW_API_KEY")

    response = httpx.post(
        settings.siliconflow_base_url,
        headers={
            "Authorization": f"Bearer {settings.siliconflow_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.siliconflow_model,
            "messages": messages,
            "temperature": 0.2,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()
```

**步骤 4: 更新 ollama.py 使用 /api/chat**

替换 `service/src/voice_text_organizer/providers/ollama.py`：

```python
from __future__ import annotations

import httpx

from voice_text_organizer.config import Settings


def rewrite_with_ollama(messages: list[dict[str, str]], settings: Settings) -> str:
    response = httpx.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": messages,
            "stream": False,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["message"]["content"].strip()
```

**步骤 5: 运行测试验证通过**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_siliconflow.py tests/test_ollama.py -v`
预期：全部通过

**步骤 6: 提交**

```bash
git add service/src/voice_text_organizer/providers/siliconflow.py service/src/voice_text_organizer/providers/ollama.py service/tests/test_siliconflow.py service/tests/test_ollama.py
git commit -m "feat: update providers to accept messages list instead of prompt string"
```

---

### 任务 8: 更新 router 类型签名

**文件：**
- 修改：`service/src/voice_text_organizer/router.py`
- 测试：`service/tests/test_router.py`

**步骤 1: 编写失败的测试**

在 `service/tests/test_router.py` 中添加：

```python
def test_route_rewrite_passes_messages_to_cloud():
    messages = [{"role": "system", "content": "hi"}, {"role": "user", "content": "test"}]
    called_with = {}

    def mock_cloud(msgs):
        called_with["messages"] = msgs
        return "result"

    result = route_rewrite(messages, cloud_fn=mock_cloud, local_fn=lambda m: "", default_mode="cloud")
    assert result == "result"
    assert called_with["messages"] == messages
```

**步骤 2: 运行测试验证失败**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_router.py -v -k "messages"`
预期：可能通过或失败，取决于现有测试。关键是类型注解已更新。

**步骤 3: 更新 router.py**

替换 `service/src/voice_text_organizer/router.py`：

```python
from __future__ import annotations

from typing import Callable

Messages = list[dict[str, str]]


def route_rewrite(
    messages: Messages,
    cloud_fn: Callable[[Messages], str],
    local_fn: Callable[[Messages], str],
    default_mode: str = "cloud",
    fallback: bool = True,
) -> str:
    if default_mode == "local":
        return local_fn(messages)

    try:
        return cloud_fn(messages)
    except Exception:
        if fallback:
            return local_fn(messages)
        raise
```

**步骤 4: 运行测试验证通过**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_router.py -v`
预期：全部通过

**步骤 5: 提交**

```bash
git add service/src/voice_text_organizer/router.py service/tests/test_router.py
git commit -m "refactor: update router to use messages list type signature"
```

---

### 任务 9: 在 main.py 中连接 existing_text

**文件：**
- 修改：`service/src/voice_text_organizer/main.py:215-228,254-296`
- 测试：`service/tests/test_record_api.py`

**步骤 1: 编写失败的测试**

在 `service/tests/test_record_api.py` 中添加：

```python
def test_start_record_accepts_existing_text(client, mock_recorder):
    response = client.post("/v1/record/start", json={
        "selected_text": None,
        "existing_text": "前面已有的文字",
    })
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    # 验证 existing_text 存储在 session 中
    from voice_text_organizer.main import store
    session = store.get(session_id)
    assert session.existing_text == "前面已有的文字"
```

**步骤 2: 运行测试验证失败**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_record_api.py -v -k "existing_text"`
预期：FAIL — `start_record` 没有将 `existing_text` 传递给 `store.create()`。

**步骤 3: 更新 main.py**

更新 `start_record()`（约第 222-228 行）：
```python
@app.post("/v1/record/start", response_model=StartSessionResponse)
def start_record(payload: StartSessionRequest) -> StartSessionResponse:
    session_id = store.create(
        selected_text=payload.selected_text,
        existing_text=payload.existing_text,
    )
    try:
        recorder.start(session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to start recording: {exc}") from exc
    return StartSessionResponse(session_id=session_id)
```

更新 `start_session()`（约第 215-218 行）：
```python
@app.post("/v1/session/start", response_model=StartSessionResponse)
def start_session(payload: StartSessionRequest) -> StartSessionResponse:
    session_id = store.create(
        selected_text=payload.selected_text,
        existing_text=payload.existing_text,
    )
    return StartSessionResponse(session_id=session_id)
```

更新 `stop_record()` — 修改 `build_prompt` 调用（约第 278 行）：
```python
        prompt = build_prompt(
            voice_text,
            selected_text=session.selected_text,
            existing_text=session.existing_text,
        )
```

注意：`prompt` 现在是 messages 列表。`route_rewrite` 和 providers 已接受 messages。

更新 `cloud_provider` 和 `local_provider`（约第 117-122 行）：
```python
def cloud_provider(messages: list[dict[str, str]]) -> str:
    return rewrite_with_siliconflow(messages, settings=settings)


def local_provider(messages: list[dict[str, str]]) -> str:
    return rewrite_with_ollama(messages, settings=settings)
```

同样更新 `stop_session()`（约第 242 行）：
```python
        prompt = build_prompt(
            voice_text,
            selected_text=session.selected_text,
            existing_text=session.existing_text,
        )
```

**步骤 4: 运行测试验证通过**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/ -v`
预期：全部通过

**步骤 5: 提交**

```bash
git add service/src/voice_text_organizer/main.py service/tests/test_record_api.py
git commit -m "feat: wire existing_text through session to build_prompt for context-aware rewriting"
```

---

### 任务 10: 将默认模型更新为 DeepSeek-V3

**文件：**
- 修改：`service/src/voice_text_organizer/config.py:13`
- 测试：`service/tests/test_config.py`

**步骤 1: 编写测试**

在 `service/tests/test_config.py` 中添加（如果不存在则创建）：

```python
from voice_text_organizer.config import Settings


def test_default_model_is_deepseek_v3():
    s = Settings(siliconflow_api_key="test-key")
    assert s.siliconflow_model == "deepseek-ai/DeepSeek-V3"
```

**步骤 2: 运行测试验证失败**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_config.py -v -k "deepseek"`
预期：FAIL — 默认仍是 `Qwen/Qwen2.5-7B-Instruct`。

**步骤 3: 更新 config.py**

更改 `service/src/voice_text_organizer/config.py` 第 13 行：
```python
    siliconflow_model: str = "deepseek-ai/DeepSeek-V3"
```

**步骤 4: 运行测试验证通过**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_config.py -v`
预期：全部通过

**步骤 5: 提交**

```bash
git add service/src/voice_text_organizer/config.py service/tests/test_config.py
git commit -m "feat: switch default LLM to DeepSeek-V3 for better quality and speed"
```

---

### 任务 11: 修复因重构而破坏的现有测试

**文件：**
- 修改：`service/tests/` 下的各种测试文件

**步骤 1: 运行完整测试套件**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/ -v`

识别由以下原因导致的任何失败：
- `build_prompt` 现在返回 `list[dict]` 而不是 `str`
- Provider 函数现在期望 `list[dict]` 而不是 `str`
- Router 现在传递 `list[dict]` 而不是 `str`
- Ollama 使用 `/api/chat` 而不是 `/api/generate`

**步骤 2: 修复每个失败的测试**

更新损坏的测试以使用新的 messages 列表格式。常见需要的更改：
- 调用 `build_prompt()` 并对返回的字符串进行断言的测试 → 对 `messages[1]["content"]` 进行断言
- 用 `str` 参数 mock providers 的测试 → 用 `list[dict]` 参数 mock
- mock Ollama `/api/generate` 的测试 → mock `/api/chat` 并使用 `{"message": {"content": "..."}}`

**步骤 3: 再次运行完整测试套件**

运行：`cd /d "E:\AI项目\typeless\service" && python -m pytest tests/ -v`
预期：全部通过

**步骤 4: 提交**

```bash
git add service/tests/
git commit -m "fix: update existing tests for messages-list refactoring"
```

---

### 任务 12: 端到端冒烟测试

**步骤 1: 启动后端服务**

运行：`cd /d "E:\AI项目\typeless" && powershell -ExecutionPolicy Bypass -File scripts/run-service.ps1`

**步骤 2: 测试独立模式（无上下文）**

```bash
curl -X POST http://127.0.0.1:8775/v1/record/start -H "Content-Type: application/json" -d "{\"selected_text\": null, \"existing_text\": null}"
```

验证：返回 `session_id`。

**步骤 3: 测试续写模式**

```bash
curl -X POST http://127.0.0.1:8775/v1/record/start -H "Content-Type: application/json" -d "{\"selected_text\": null, \"existing_text\": \"前面已有的内容\"}"
```

验证：返回 `session_id`。session 存储了 `existing_text`。

**步骤 4: 测试设置显示新默认模型**

```bash
curl http://127.0.0.1:8775/v1/settings
```

验证：响应显示服务以云模式配置运行。

**步骤 5: 最终提交**

无需代码更改。再次验证所有测试通过：

```bash
cd /d "E:\AI项目\typeless\service" && python -m pytest tests/ -v
```

预期：全部通过 — 实现完成。
