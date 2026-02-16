# 修复文字覆盖 + 上下文续写 + 提速提质 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复三个问题：(1) 录音后原有文字被覆盖 (2) 续写时缺乏上下文理解 (3) 改写速度和质量不够好。

**Architecture:** AHK 端修复焦点抢占和文字获取逻辑；Python 后端增加 `existing_text` 上下文传递，重构 prompt 为 messages 格式并支持续写/选中/独立三种模式，升级默认 LLM 为 DeepSeek-V3。

**Tech Stack:** AutoHotkey v2, Python 3.10+, FastAPI, Pydantic v2, httpx, pytest, pytest-mock.

---

## Skills To Apply During Execution

- `@test-driven-development` for every Python step.
- `@systematic-debugging` if any test or integration behavior fails.
- `@verification-before-completion` before claiming done.

---

### Task 1: Fix waveform GUI focus stealing

**Files:**
- Modify: `desktop/hotkey_agent.ahk:219` (InitWaveformGui)

**Step 1: Modify waveform GUI creation to prevent focus stealing**

In `InitWaveformGui()`, line 219, change:
```ahk
waveformGui := Gui("-Caption +ToolWindow +AlwaysOnTop +E0x20")
```
to:
```ahk
waveformGui := Gui("-Caption +ToolWindow +AlwaysOnTop +E0x20 +E0x08000000")
```

`E0x08000000` is `WS_EX_NOACTIVATE` — prevents the window from ever becoming the foreground window and stealing focus.

**Step 2: Verify waveform still shows with `NA` flag**

Confirm that `ShowWaveformIndicator()` at line 247 already uses `"NA"` option in `waveformGui.Show()`. `NA` means "no activate" during Show. The `+E0x08000000` adds OS-level guarantee even on click or other events.

Line 247 already has: `waveformGui.Show("NA x" . x . " y" . y)` — confirmed OK.

**Step 3: Commit**

```bash
git add desktop/hotkey_agent.ahk
git commit -m "fix: prevent waveform GUI from stealing focus (WS_EX_NOACTIVATE)"
```

---

### Task 2: Fix InsertText to preserve existing text

**Files:**
- Modify: `desktop/hotkey_agent.ahk:894-951` (InsertText)

**Step 1: Add deselect safety in InsertText before pasting**

In `InsertText()`, after the `Sleep(80)` on line 905, before the clipboard paste logic on line 907, add:

```ahk
    ; Deselect any auto-selected text to prevent overwriting existing content.
    Send("{End}")
    Sleep(50)
```

The full updated section (lines 904-907) becomes:
```ahk
    ; Give the foreground app a brief moment to regain focus after hotkey release.
    Sleep(80)

    ; Deselect any auto-selected text to prevent overwriting existing content.
    Send("{End}")
    Sleep(50)

    clipSaved := ClipboardAll()
```

**Step 2: Commit**

```bash
git add desktop/hotkey_agent.ahk
git commit -m "fix: deselect text before paste to prevent overwriting existing content"
```

---

### Task 3: Add GetFullTextSafe function to AHK

**Files:**
- Modify: `desktop/hotkey_agent.ahk` (after `GetSelectedTextSafe`, ~line 892)

**Step 1: Add GetFullTextSafe function**

Insert after `GetSelectedTextSafe()` (after line 892):

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
        ; Deselect and move cursor to end
        Send("{End}")
    }
    finally
    {
        A_Clipboard := clipSaved
    }
    return fullText
}
```

**Step 2: Commit**

```bash
git add desktop/hotkey_agent.ahk
git commit -m "feat: add GetFullTextSafe to capture all text in input field"
```

---

### Task 4: Modify StartRecordingSession to capture existing text

**Files:**
- Modify: `desktop/hotkey_agent.ahk:100-130` (StartRecordingSession)
- Modify: `desktop/hotkey_agent.ahk:953-958` (ApiStartRecord)

**Step 1: Update StartRecordingSession to capture existing text**

Replace lines 105-108:
```ahk
        PausePlaybackForRecording()
        targetWindowId := WinExist("A")
        selectedText := GetSelectedTextSafe()
        sessionId := ApiStartRecord(selectedText)
```

With:
```ahk
        PausePlaybackForRecording()
        targetWindowId := WinExist("A")
        selectedText := GetSelectedTextSafe()
        existingText := ""
        if (selectedText = "")
            existingText := GetFullTextSafe()
        sessionId := ApiStartRecord(selectedText, existingText)
```

**Step 2: Update ApiStartRecord to send existing_text**

Replace lines 953-958:
```ahk
ApiStartRecord(selectedText)
{
    q := Chr(34)
    payload := "{" . q . "selected_text" . q . ":" . q . JsonEscape(selectedText) . q . "}"
    response := HttpPost("/v1/record/start", payload)
    return ExtractJsonString(response, "session_id")
}
```

With:
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

**Step 3: Commit**

```bash
git add desktop/hotkey_agent.ahk
git commit -m "feat: capture existing text and send to backend for context-aware rewriting"
```

---

### Task 5: Add existing_text to schemas and session store

**Files:**
- Modify: `service/src/voice_text_organizer/schemas.py:8-9`
- Modify: `service/src/voice_text_organizer/session_store.py:8-11,19`
- Test: `service/tests/test_session_store.py`

**Step 1: Write the failing test**

Add test to `service/tests/test_session_store.py`:

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

**Step 2: Run test to verify it fails**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_session_store.py -v -k "existing_text"`
Expected: FAIL — `create()` doesn't accept `existing_text` parameter.

**Step 3: Update schemas.py**

In `service/src/voice_text_organizer/schemas.py`, change `StartSessionRequest` (lines 8-9):
```python
class StartSessionRequest(BaseModel):
    selected_text: str | None = None
    existing_text: str | None = None
```

**Step 4: Update session_store.py**

In `service/src/voice_text_organizer/session_store.py`:

Update `Session` dataclass (lines 8-11):
```python
@dataclass
class Session:
    session_id: str
    selected_text: str | None = None
    existing_text: str | None = None
```

Update `create` method (line 19):
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

**Step 5: Run test to verify it passes**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_session_store.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add service/src/voice_text_organizer/schemas.py service/src/voice_text_organizer/session_store.py service/tests/test_session_store.py
git commit -m "feat: add existing_text field to session schema and store"
```

---

### Task 6: Refactor build_prompt to return messages list with three modes

**Files:**
- Modify: `service/src/voice_text_organizer/rewrite.py`
- Test: `service/tests/test_rewrite.py`

**Step 1: Write the failing tests**

Add/replace tests in `service/tests/test_rewrite.py`:

```python
from voice_text_organizer.rewrite import build_prompt, postprocess_rewrite_output


def test_build_prompt_standalone_mode():
    """No context — independent rewrite."""
    messages = build_prompt("今天天气真不错我想出去走走")
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "今天天气真不错" in messages[1]["content"]
    # Should NOT mention existing text or selected text
    assert "已有文字" not in messages[1]["content"]
    assert "existing" not in messages[1]["content"].lower()


def test_build_prompt_selected_text_mode():
    """Selected text — refine/replace mode."""
    messages = build_prompt("把这段改成更正式的", selected_text="嗨大家好")
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "嗨大家好" in messages[1]["content"]
    assert "把这段改成更正式的" in messages[1]["content"]


def test_build_prompt_continuation_mode():
    """Has existing_text but no selected_text — continuation mode."""
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
    """existing_text over 2000 chars gets truncated to last 2000."""
    long_text = "这是很长的文字。" * 500  # 4000 chars
    messages = build_prompt("继续写", existing_text=long_text)
    user_content = messages[1]["content"]
    # The existing text in prompt should be truncated
    assert len(long_text) > 2000
    # We can't check exact chars because it's embedded in prompt,
    # but the full 4000-char string should NOT appear verbatim
    assert long_text not in user_content


def test_build_prompt_selected_text_takes_priority_over_existing():
    """When both selected_text and existing_text are provided, selected_text mode is used."""
    messages = build_prompt(
        "改成英文",
        selected_text="你好世界",
        existing_text="前面的内容",
    )
    user_content = messages[1]["content"]
    assert "你好世界" in user_content
    # existing_text is ignored when selected_text is present
    assert "前面的内容" not in user_content
```

**Step 2: Run tests to verify they fail**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_rewrite.py -v -k "build_prompt"`
Expected: FAIL — `build_prompt` returns `str` not `list`.

**Step 3: Rewrite build_prompt and simplify rewrite.py**

Replace the entire `build_prompt` function and update `SYSTEM_RULES` in `service/src/voice_text_organizer/rewrite.py`:

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

**Step 4: Run tests to verify they pass**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_rewrite.py -v -k "build_prompt"`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/rewrite.py service/tests/test_rewrite.py
git commit -m "feat: refactor build_prompt to messages list with standalone/selected/continuation modes"
```

---

### Task 7: Update providers to accept messages list

**Files:**
- Modify: `service/src/voice_text_organizer/providers/siliconflow.py`
- Modify: `service/src/voice_text_organizer/providers/ollama.py`
- Test: `service/tests/test_siliconflow.py`
- Test: `service/tests/test_ollama.py`

**Step 1: Write the failing tests**

Update test for siliconflow in `service/tests/test_siliconflow.py` — find existing tests and update the mock call to pass a messages list instead of a string. Add a test like:

```python
def test_rewrite_sends_messages_list(mock_httpx_post):
    """Provider should forward the messages list directly."""
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "Test input"},
    ]
    result = rewrite_with_siliconflow(messages, settings=settings)
    call_json = mock_httpx_post.call_args.kwargs["json"]
    assert call_json["messages"] == messages
```

Similarly for ollama in `service/tests/test_ollama.py`:

```python
def test_rewrite_sends_messages_to_chat_api(mock_httpx_post):
    """Provider should use /api/chat and forward messages list."""
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

**Step 2: Run tests to verify they fail**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_siliconflow.py tests/test_ollama.py -v -k "messages"`
Expected: FAIL — providers still expect `str` param.

**Step 3: Update siliconflow.py**

Replace `service/src/voice_text_organizer/providers/siliconflow.py`:

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

**Step 4: Update ollama.py to use /api/chat**

Replace `service/src/voice_text_organizer/providers/ollama.py`:

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

**Step 5: Run tests to verify they pass**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_siliconflow.py tests/test_ollama.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add service/src/voice_text_organizer/providers/siliconflow.py service/src/voice_text_organizer/providers/ollama.py service/tests/test_siliconflow.py service/tests/test_ollama.py
git commit -m "feat: update providers to accept messages list instead of prompt string"
```

---

### Task 8: Update router type signatures

**Files:**
- Modify: `service/src/voice_text_organizer/router.py`
- Test: `service/tests/test_router.py`

**Step 1: Write the failing test**

Add to `service/tests/test_router.py`:

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

**Step 2: Run test to verify it fails**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_router.py -v -k "messages"`
Expected: May pass or fail depending on existing tests. The key is that the type annotation is updated.

**Step 3: Update router.py**

Replace `service/src/voice_text_organizer/router.py`:

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

**Step 4: Run tests to verify they pass**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_router.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/router.py service/tests/test_router.py
git commit -m "refactor: update router to use messages list type signature"
```

---

### Task 9: Wire existing_text through main.py

**Files:**
- Modify: `service/src/voice_text_organizer/main.py:215-228,254-296`
- Test: `service/tests/test_record_api.py`

**Step 1: Write the failing test**

Add to `service/tests/test_record_api.py`:

```python
def test_start_record_accepts_existing_text(client, mock_recorder):
    response = client.post("/v1/record/start", json={
        "selected_text": None,
        "existing_text": "前面已有的文字",
    })
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    # Verify existing_text is stored in session
    from voice_text_organizer.main import store
    session = store.get(session_id)
    assert session.existing_text == "前面已有的文字"
```

**Step 2: Run test to verify it fails**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_record_api.py -v -k "existing_text"`
Expected: FAIL — `start_record` doesn't pass `existing_text` to `store.create()`.

**Step 3: Update main.py**

Update `start_record()` (around line 222-228):
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

Update `start_session()` (around line 215-218):
```python
@app.post("/v1/session/start", response_model=StartSessionResponse)
def start_session(payload: StartSessionRequest) -> StartSessionResponse:
    session_id = store.create(
        selected_text=payload.selected_text,
        existing_text=payload.existing_text,
    )
    return StartSessionResponse(session_id=session_id)
```

Update `stop_record()` — change `build_prompt` call (around line 278):
```python
        prompt = build_prompt(
            voice_text,
            selected_text=session.selected_text,
            existing_text=session.existing_text,
        )
```

Note: `prompt` is now a messages list. The `route_rewrite` and providers already accept messages.

Update `cloud_provider` and `local_provider` (around lines 117-122):
```python
def cloud_provider(messages: list[dict[str, str]]) -> str:
    return rewrite_with_siliconflow(messages, settings=settings)


def local_provider(messages: list[dict[str, str]]) -> str:
    return rewrite_with_ollama(messages, settings=settings)
```

Same update for `stop_session()` (around line 242):
```python
        prompt = build_prompt(
            voice_text,
            selected_text=session.selected_text,
            existing_text=session.existing_text,
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/main.py service/tests/test_record_api.py
git commit -m "feat: wire existing_text through session to build_prompt for context-aware rewriting"
```

---

### Task 10: Update default model to DeepSeek-V3

**Files:**
- Modify: `service/src/voice_text_organizer/config.py:13`
- Test: `service/tests/test_config.py`

**Step 1: Write the test**

Add to `service/tests/test_config.py` (create if not exists):

```python
from voice_text_organizer.config import Settings


def test_default_model_is_deepseek_v3():
    s = Settings(siliconflow_api_key="test-key")
    assert s.siliconflow_model == "deepseek-ai/DeepSeek-V3"
```

**Step 2: Run test to verify it fails**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_config.py -v -k "deepseek"`
Expected: FAIL — default is still `Qwen/Qwen2.5-7B-Instruct`.

**Step 3: Update config.py**

Change line 13 in `service/src/voice_text_organizer/config.py`:
```python
    siliconflow_model: str = "deepseek-ai/DeepSeek-V3"
```

**Step 4: Run test to verify it passes**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/test_config.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/config.py service/tests/test_config.py
git commit -m "feat: switch default LLM to DeepSeek-V3 for better quality and speed"
```

---

### Task 11: Fix existing tests that break from refactoring

**Files:**
- Modify: Various test files under `service/tests/`

**Step 1: Run full test suite**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/ -v`

Identify any failures caused by:
- `build_prompt` now returning `list[dict]` instead of `str`
- Provider functions now expecting `list[dict]` instead of `str`
- Router now passing `list[dict]` instead of `str`
- Ollama using `/api/chat` instead of `/api/generate`

**Step 2: Fix each broken test**

Update broken tests to use the new messages list format. Common changes needed:
- Tests that call `build_prompt()` and assert on the returned string → assert on `messages[1]["content"]`
- Tests that mock providers with `str` arg → mock with `list[dict]` arg
- Tests that mock Ollama `/api/generate` → mock `/api/chat` with `{"message": {"content": "..."}}`

**Step 3: Run full test suite again**

Run: `cd /d "E:\AI项目\typeless\service" && python -m pytest tests/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add service/tests/
git commit -m "fix: update existing tests for messages-list refactoring"
```

---

### Task 12: End-to-end smoke test

**Step 1: Start the backend service**

Run: `cd /d "E:\AI项目\typeless" && powershell -ExecutionPolicy Bypass -File scripts/run-service.ps1`

**Step 2: Test standalone mode (no context)**

```bash
curl -X POST http://127.0.0.1:8775/v1/record/start -H "Content-Type: application/json" -d "{\"selected_text\": null, \"existing_text\": null}"
```

Verify: Returns `session_id`.

**Step 3: Test continuation mode**

```bash
curl -X POST http://127.0.0.1:8775/v1/record/start -H "Content-Type: application/json" -d "{\"selected_text\": null, \"existing_text\": \"前面已有的内容\"}"
```

Verify: Returns `session_id`. The session stores `existing_text`.

**Step 4: Test settings show new default model**

```bash
curl http://127.0.0.1:8775/v1/settings
```

Verify: Response shows the service is running with cloud mode configured.

**Step 5: Final commit**

No code changes needed. Verify all tests pass one more time:

```bash
cd /d "E:\AI项目\typeless\service" && python -m pytest tests/ -v
```

Expected: ALL PASS — implementation complete.
