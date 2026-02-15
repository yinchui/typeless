# Voice Text Organizer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Windows background tool that records voice on long-press `Alt`, converts speech to text, rewrites it into clear structured language, and inserts/replaces text at the current cursor automatically.

**Architecture:** Use `AutoHotkey v2` as the input/injection layer and a local `Python FastAPI` service as the intelligence layer. AHK handles global hotkey, selected-text capture, and text insertion; Python handles recording lifecycle, ASR, rewrite, and cloud/local model routing with configurable fallback.

**Tech Stack:** AutoHotkey v2, Python 3.11+, FastAPI, Uvicorn, Pydantic v2, httpx, pytest, pytest-mock.

---

## Assumptions

- Platform is Windows only (MVP).
- Default rewrite provider is SiliconFlow cloud API.
- Local provider is Ollama (`http://localhost:11434`).
- API key is loaded from env var `SILICONFLOW_API_KEY` only.

## Project Structure Target

- `desktop/hotkey_agent.ahk`
- `service/pyproject.toml`
- `service/src/voice_text_organizer/__init__.py`
- `service/src/voice_text_organizer/main.py`
- `service/src/voice_text_organizer/config.py`
- `service/src/voice_text_organizer/schemas.py`
- `service/src/voice_text_organizer/session_store.py`
- `service/src/voice_text_organizer/audio.py`
- `service/src/voice_text_organizer/asr.py`
- `service/src/voice_text_organizer/rewrite.py`
- `service/src/voice_text_organizer/router.py`
- `service/src/voice_text_organizer/providers/siliconflow.py`
- `service/src/voice_text_organizer/providers/ollama.py`
- `service/tests/...`

## Skills To Apply During Execution

- `@test-driven-development` for every feature step.
- `@systematic-debugging` if any test or integration behavior fails.
- `@verification-before-completion` before claiming done.

### Task 1: Bootstrap Python service and health endpoint

**Files:**
- Create: `service/pyproject.toml`
- Create: `service/src/voice_text_organizer/main.py`
- Create: `service/tests/test_health.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient
from voice_text_organizer.main import app

def test_health():
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
```

**Step 2: Run test to verify it fails**

Run: `cd service; pytest tests/test_health.py::test_health -v`
Expected: FAIL with `ModuleNotFoundError` or missing route.

**Step 3: Write minimal implementation**

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
```

**Step 4: Run test to verify it passes**

Run: `cd service; pytest tests/test_health.py::test_health -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add service/pyproject.toml service/src/voice_text_organizer/main.py service/tests/test_health.py
git commit -m "chore: bootstrap fastapi service with health endpoint"
```

### Task 2: Add settings and secure API key loading

**Files:**
- Create: `service/src/voice_text_organizer/config.py`
- Create: `service/tests/test_config.py`

**Step 1: Write the failing test**

```python
import os
import pytest
from voice_text_organizer.config import Settings

def test_cloud_mode_requires_api_key(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    with pytest.raises(ValueError):
        Settings(default_mode="cloud")
```

**Step 2: Run test to verify it fails**

Run: `cd service; pytest tests/test_config.py::test_cloud_mode_requires_api_key -v`
Expected: FAIL because `Settings` is undefined.

**Step 3: Write minimal implementation**

```python
from pydantic import BaseModel
import os

class Settings(BaseModel):
    default_mode: str = "cloud"
    siliconflow_api_key: str | None = os.getenv("SILICONFLOW_API_KEY")

    def __init__(self, **data):
        super().__init__(**data)
        if self.default_mode == "cloud" and not self.siliconflow_api_key:
            raise ValueError("SILICONFLOW_API_KEY is required in cloud mode")
```

**Step 4: Run test to verify it passes**

Run: `cd service; pytest tests/test_config.py::test_cloud_mode_requires_api_key -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/config.py service/tests/test_config.py
git commit -m "feat: add secure environment-based settings"
```

### Task 3: Define API schemas and session store

**Files:**
- Create: `service/src/voice_text_organizer/schemas.py`
- Create: `service/src/voice_text_organizer/session_store.py`
- Create: `service/tests/test_session_store.py`

**Step 1: Write the failing test**

```python
from voice_text_organizer.session_store import SessionStore

def test_create_and_get_session():
    store = SessionStore()
    sid = store.create(selected_text="old text")
    session = store.get(sid)
    assert session.selected_text == "old text"
```

**Step 2: Run test to verify it fails**

Run: `cd service; pytest tests/test_session_store.py::test_create_and_get_session -v`
Expected: FAIL due to missing store implementation.

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from uuid import uuid4

@dataclass
class Session:
    session_id: str
    selected_text: str | None = None

class SessionStore:
    def __init__(self):
        self._data = {}
    def create(self, selected_text=None):
        sid = str(uuid4())
        self._data[sid] = Session(session_id=sid, selected_text=selected_text)
        return sid
    def get(self, sid):
        return self._data[sid]
```

**Step 4: Run test to verify it passes**

Run: `cd service; pytest tests/test_session_store.py::test_create_and_get_session -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/schemas.py service/src/voice_text_organizer/session_store.py service/tests/test_session_store.py
git commit -m "feat: add session schemas and in-memory session store"
```

### Task 4: Add rewrite prompt builder (general cleanup style)

**Files:**
- Create: `service/src/voice_text_organizer/rewrite.py`
- Create: `service/tests/test_rewrite_prompt.py`

**Step 1: Write the failing test**

```python
from voice_text_organizer.rewrite import build_prompt

def test_build_prompt_includes_selected_context():
    prompt = build_prompt("new voice", selected_text="old sentence")
    assert "old sentence" in prompt
    assert "new voice" in prompt
    assert "do not add facts" in prompt.lower()
```

**Step 2: Run test to verify it fails**

Run: `cd service; pytest tests/test_rewrite_prompt.py::test_build_prompt_includes_selected_context -v`
Expected: FAIL due to missing function.

**Step 3: Write minimal implementation**

```python
def build_prompt(voice_text: str, selected_text: str | None = None) -> str:
    base = (
        "Rewrite the input into concise, logical text. "
        "Remove filler words and redundancy, preserve intent, do not add facts."
    )
    if selected_text:
        return f"{base}\nSelected text:\n{selected_text}\nNew voice instruction:\n{voice_text}"
    return f"{base}\nVoice text:\n{voice_text}"
```

**Step 4: Run test to verify it passes**

Run: `cd service; pytest tests/test_rewrite_prompt.py::test_build_prompt_includes_selected_context -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/rewrite.py service/tests/test_rewrite_prompt.py
git commit -m "feat: add generic rewrite prompt builder"
```

### Task 5: Implement cloud/local rewrite providers and router

**Files:**
- Create: `service/src/voice_text_organizer/providers/siliconflow.py`
- Create: `service/src/voice_text_organizer/providers/ollama.py`
- Create: `service/src/voice_text_organizer/router.py`
- Create: `service/tests/test_router.py`

**Step 1: Write the failing test**

```python
from voice_text_organizer.router import route_rewrite

def test_router_fallback_to_local_when_cloud_fails(mocker):
    cloud = mocker.Mock(side_effect=RuntimeError("cloud down"))
    local = mocker.Mock(return_value="local result")
    out = route_rewrite("hello", cloud_fn=cloud, local_fn=local, default_mode="cloud", fallback=True)
    assert out == "local result"
```

**Step 2: Run test to verify it fails**

Run: `cd service; pytest tests/test_router.py::test_router_fallback_to_local_when_cloud_fails -v`
Expected: FAIL due to missing routing function.

**Step 3: Write minimal implementation**

```python
def route_rewrite(text, cloud_fn, local_fn, default_mode="cloud", fallback=True):
    if default_mode == "local":
        return local_fn(text)
    try:
        return cloud_fn(text)
    except Exception:
        if fallback:
            return local_fn(text)
        raise
```

**Step 4: Run test to verify it passes**

Run: `cd service; pytest tests/test_router.py::test_router_fallback_to_local_when_cloud_fails -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/providers/siliconflow.py service/src/voice_text_organizer/providers/ollama.py service/src/voice_text_organizer/router.py service/tests/test_router.py
git commit -m "feat: add rewrite routing with cloud-to-local fallback"
```

### Task 6: Implement API endpoints for start/stop workflow

**Files:**
- Modify: `service/src/voice_text_organizer/main.py`
- Create: `service/tests/test_session_api.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient
from voice_text_organizer.main import app

def test_start_and_stop_returns_final_text():
    client = TestClient(app)
    res_start = client.post("/v1/session/start", json={"selected_text": "old"})
    assert res_start.status_code == 200
    sid = res_start.json()["session_id"]
    res_stop = client.post("/v1/session/stop", json={"session_id": sid, "voice_text": "rewrite this"})
    assert res_stop.status_code == 200
    assert "final_text" in res_stop.json()
```

**Step 2: Run test to verify it fails**

Run: `cd service; pytest tests/test_session_api.py::test_start_and_stop_returns_final_text -v`
Expected: FAIL because endpoints are missing.

**Step 3: Write minimal implementation**

```python
@app.post("/v1/session/start")
def start(payload: StartSessionRequest):
    sid = store.create(selected_text=payload.selected_text)
    return {"session_id": sid}

@app.post("/v1/session/stop")
def stop(payload: StopSessionRequest):
    session = store.get(payload.session_id)
    prompt = build_prompt(payload.voice_text, selected_text=session.selected_text)
    final_text = route_rewrite(prompt, cloud_fn=cloud_provider, local_fn=local_provider, default_mode=settings.default_mode, fallback=True)
    return {"final_text": final_text}
```

**Step 4: Run test to verify it passes**

Run: `cd service; pytest tests/test_session_api.py::test_start_and_stop_returns_final_text -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/main.py service/tests/test_session_api.py
git commit -m "feat: add start/stop API for one-shot rewrite workflow"
```

### Task 7: Add AHK long-press Alt recording flow and insertion

**Files:**
- Create: `desktop/hotkey_agent.ahk`
- Create: `desktop/README.md`

**Step 1: Write the failing check**

```text
Manual test script:
1) Run hotkey_agent.ahk
2) Focus Notepad
3) Long-press Alt and release
4) Expected: API call is attempted, result text inserted at cursor
Current: no script behavior exists
```

**Step 2: Run check to verify it fails**

Run: `AutoHotkey64.exe desktop\\hotkey_agent.ahk`
Expected: fail/no action (script not present yet).

**Step 3: Write minimal implementation**

```ahk
#SingleInstance Force
global pressTick := 0
global longPressMs := 250

~Alt::
{
    pressTick := A_TickCount
}

~Alt Up::
{
    if (A_TickCount - pressTick < longPressMs)
        return
    ; 1) read selected text (clipboard-safe)
    ; 2) call /v1/session/start then /v1/session/stop
    ; 3) send final text to active cursor
}
```

**Step 4: Run check to verify it passes**

Run: `AutoHotkey64.exe desktop\\hotkey_agent.ahk`
Expected: long-press triggers HTTP flow and inserts returned text.

**Step 5: Commit**

```bash
git add desktop/hotkey_agent.ahk desktop/README.md
git commit -m "feat: add windows hotkey agent for long-press alt workflow"
```

### Task 8: Add ASR adapter interface and integration seam

**Files:**
- Create: `service/src/voice_text_organizer/asr.py`
- Create: `service/tests/test_asr.py`
- Modify: `service/src/voice_text_organizer/main.py`

**Step 1: Write the failing test**

```python
from voice_text_organizer.asr import normalize_asr_text

def test_normalize_asr_text_strips_whitespace():
    assert normalize_asr_text("  hello world  ") == "hello world"
```

**Step 2: Run test to verify it fails**

Run: `cd service; pytest tests/test_asr.py::test_normalize_asr_text_strips_whitespace -v`
Expected: FAIL due to missing function.

**Step 3: Write minimal implementation**

```python
def normalize_asr_text(text: str) -> str:
    return " ".join(text.strip().split())
```

**Step 4: Run test to verify it passes**

Run: `cd service; pytest tests/test_asr.py::test_normalize_asr_text_strips_whitespace -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/asr.py service/src/voice_text_organizer/main.py service/tests/test_asr.py
git commit -m "feat: add asr adapter seam and normalization utility"
```

### Task 9: End-to-end API test with mocks

**Files:**
- Create: `service/tests/test_e2e_mocked.py`
- Modify: `service/src/voice_text_organizer/main.py`

**Step 1: Write the failing test**

```python
def test_e2e_session_flow_with_mocked_dependencies(client, mocker):
    mocker.patch("voice_text_organizer.main.cloud_provider", return_value="clean result")
    s = client.post("/v1/session/start", json={"selected_text": "old"}).json()["session_id"]
    out = client.post("/v1/session/stop", json={"session_id": s, "voice_text": "new idea"}).json()
    assert out["final_text"] == "clean result"
```

**Step 2: Run test to verify it fails**

Run: `cd service; pytest tests/test_e2e_mocked.py::test_e2e_session_flow_with_mocked_dependencies -v`
Expected: FAIL due to unresolved dependencies or fixtures.

**Step 3: Write minimal implementation**

```python
# Add reusable TestClient fixture and dependency seams for providers/store in main.py
# Ensure endpoint code paths are mockable without real network/audio calls.
```

**Step 4: Run test to verify it passes**

Run: `cd service; pytest tests/test_e2e_mocked.py::test_e2e_session_flow_with_mocked_dependencies -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/main.py service/tests/test_e2e_mocked.py
git commit -m "test: add mocked end-to-end session flow verification"
```

### Task 10: Verification checklist, scripts, and docs

**Files:**
- Create: `README.md`
- Create: `service/.env.example`
- Create: `scripts/run-dev.ps1`
- Create: `scripts/run-tests.ps1`

**Step 1: Write failing docs/test command expectations**

```text
Checklist:
- New user can run service in <=5 commands
- Env var requirements are documented
- AHK startup and manual QA steps are documented
```

**Step 2: Run verification to confirm gaps**

Run: `cd service; pytest -q`
Expected: identify missing docs/scripts or setup friction.

**Step 3: Write minimal implementation**

```powershell
# scripts/run-dev.ps1
cd service
uvicorn voice_text_organizer.main:app --host 127.0.0.1 --port 8765 --reload
```

```powershell
# scripts/run-tests.ps1
cd service
pytest -v
```

**Step 4: Run full verification**

Run: `powershell -ExecutionPolicy Bypass -File scripts\\run-tests.ps1`
Expected: all tests PASS.

**Step 5: Commit**

```bash
git add README.md service/.env.example scripts/run-dev.ps1 scripts/run-tests.ps1
git commit -m "docs: add setup, run scripts, and verification checklist"
```

## Final Verification Gate

- Run: `cd service; pytest -v`
- Run: `cd service; python -m uvicorn voice_text_organizer.main:app --host 127.0.0.1 --port 8765`
- Run manual QA in Notepad:
  - Long-press `Alt` inserts rewritten text at cursor.
  - Select text + long-press `Alt` replaces selection.
  - Switch mode to local and verify Ollama path.
- Confirm no secrets are hardcoded:
  - Run: `rg -n "sk-[a-zA-Z0-9]|SILICONFLOW_API_KEY\\s*=" -S .`

