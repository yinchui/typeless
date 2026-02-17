# Transcription-First Policy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enforce transcription-first behavior so spoken questions are inserted as transcription text by default, while allowing only translation whitelist actions on selected text.

**Architecture:** Add a deterministic backend decision layer that chooses between `transcribe_only` and `selected_whitelist_rewrite` before any LLM rewrite call. Apply the same policy in both `/v1/record/stop` and `/v1/session/stop` so behavior stays consistent across recording and direct session APIs. Keep existing API schema unchanged and fallback safely to transcription if rewrite fails.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, pytest, AutoHotkey client (no protocol change).

---

## Skills to apply during execution

- `@test-driven-development`
- `@systematic-debugging`
- `@verification-before-completion`

---

### Task 1: Add decision policy module and unit tests

**Files:**
- Create: `service/src/voice_text_organizer/policy.py`
- Create: `service/tests/test_policy.py`

**Step 1: Write the failing tests**

```python
from voice_text_organizer.policy import decide_processing_mode


def test_no_selected_text_is_transcribe_only():
    mode = decide_processing_mode("你好吗", selected_text=None, existing_text="anything")
    assert mode == "transcribe_only"


def test_selected_text_with_translate_command_hits_rewrite():
    mode = decide_processing_mode("翻译成中文", selected_text="Hello", existing_text=None)
    assert mode == "selected_whitelist_rewrite"


def test_selected_text_with_non_whitelist_is_transcribe_only():
    mode = decide_processing_mode("帮我总结一下", selected_text="Hello", existing_text=None)
    assert mode == "transcribe_only"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest service/tests/test_policy.py -q`  
Expected: FAIL with missing module/function.

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

from typing import Literal

DecisionMode = Literal["transcribe_only", "selected_whitelist_rewrite"]

_TRANSLATE_PHRASES = {
    "翻译成中文", "翻成中文", "译成中文", "英译中",
    "翻译成英文", "翻成英文", "译成英文", "中译英",
    "translate to chinese", "translate to english",
}


def decide_processing_mode(voice_text: str, *, selected_text: str | None, existing_text: str | None) -> DecisionMode:
    if not (selected_text or "").strip():
        return "transcribe_only"
    normalized = _normalize_command(voice_text)
    if _is_whitelist_translation_command(normalized):
        return "selected_whitelist_rewrite"
    return "transcribe_only"
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest service/tests/test_policy.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/policy.py service/tests/test_policy.py
git commit -m "feat: add transcription-first decision policy and whitelist matcher"
```

---

### Task 2: Apply policy in `/v1/record/stop`

**Files:**
- Modify: `service/src/voice_text_organizer/main.py`
- Modify: `service/tests/test_record_api.py`

**Step 1: Write failing API tests for policy behavior**

Add tests that assert:
- no selected text -> rewrite is not called and `final_text == voice_text`
- selected text + whitelist -> rewrite is called
- selected text + non-whitelist -> rewrite not called and `final_text == voice_text`

```python
def test_record_stop_without_selected_text_never_calls_rewrite(...):
    ...
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest service/tests/test_record_api.py -q`  
Expected: FAIL because current logic still rewrites in non-whitelist cases.

**Step 3: Implement minimal endpoint change**

- Import `decide_processing_mode`.
- In `stop_record`, evaluate decision mode after `voice_text` is produced.
- Branch:
  - `transcribe_only`: `final_text = postprocess_rewrite_output(voice_text)`
  - `selected_whitelist_rewrite`: current prompt + `route_rewrite` flow
- Wrap rewrite branch with fallback to transcription on exception.

**Step 4: Run test to verify it passes**

Run: `python -m pytest service/tests/test_record_api.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/main.py service/tests/test_record_api.py
git commit -m "feat: enforce transcription-first policy in record stop endpoint"
```

---

### Task 3: Apply policy in `/v1/session/stop`

**Files:**
- Modify: `service/src/voice_text_organizer/main.py`
- Modify: `service/tests/test_session_api.py`

**Step 1: Write failing session API tests**

Add tests equivalent to record path:
- no selected text -> no rewrite
- selected text + whitelist -> rewrite allowed
- selected text + non-whitelist -> transcription only

**Step 2: Run test to verify it fails**

Run: `python -m pytest service/tests/test_session_api.py -q`  
Expected: FAIL before policy integration.

**Step 3: Implement minimal endpoint change**

- Reuse same `decide_processing_mode` call inside `stop_session`.
- Keep response schema unchanged (`final_text` only).
- Keep current `422 voice_text is empty` behavior.

**Step 4: Run test to verify it passes**

Run: `python -m pytest service/tests/test_session_api.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/main.py service/tests/test_session_api.py
git commit -m "feat: align session stop with transcription-first policy"
```

---

### Task 4: Add rewrite fallback and decision logging

**Files:**
- Modify: `service/src/voice_text_organizer/main.py`
- Modify: `service/tests/test_record_api.py`
- Modify: `service/tests/test_session_api.py`

**Step 1: Write failing tests for fallback**

Add tests where whitelist matches but `route_rewrite` raises:
- endpoint still returns `200`
- `final_text == voice_text`

**Step 2: Run tests to verify fail**

Run:  
- `python -m pytest service/tests/test_record_api.py -q`  
- `python -m pytest service/tests/test_session_api.py -q`

Expected: FAIL before fallback logic is added.

**Step 3: Implement fallback + logs**

- In rewrite branch, catch `Exception` and fallback to transcription output.
- Add lightweight log lines with:
  - `decision_mode`
  - whitelist hit status
  - error stage (`rewrite`)

**Step 4: Run tests to verify pass**

Run:
- `python -m pytest service/tests/test_record_api.py -q`
- `python -m pytest service/tests/test_session_api.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/main.py service/tests/test_record_api.py service/tests/test_session_api.py
git commit -m "feat: add safe fallback and decision logs for policy flow"
```

---

### Task 5: Full verification and release notes update

**Files:**
- Modify: `README.md`

**Step 1: Update behavior docs**

Document new user-visible rules:
- default transcription-first
- selected text translation whitelist only
- non-whitelist with selected text returns spoken transcription

**Step 2: Run full service test suite**

Run: `python -m pytest service/tests -q`  
Expected: all tests PASS.

**Step 3: Optional local smoke check**

Run:
- `start-app.cmd`
- Scenario checks:
  - ask question without selection -> transcribed question inserted
  - select English and say "翻译成中文" -> translated output

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: describe transcription-first and translation whitelist behavior"
```

**Step 5: Final verification commit**

```bash
git status --short
python -m pytest service/tests -q
```

Expected:
- clean working tree
- all tests PASS

