# Adaptive Template Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add flexible multi-template routing so the backend can auto-apply structure when confidence is high, but fallback to `light_edit` when confidence is low or execution fails.

**Architecture:** Keep selected-text translation as top-priority special branch, then apply conservative fuzzy explicit command matching, then classifier-based template selection with a confidence threshold. Reuse existing rewrite providers and endpoint schemas, and add template-aware prompt building plus deterministic fallback to `light_edit`.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, pytest, existing rewrite router/providers.

---

## Skills to apply during execution

- `@test-driven-development`
- `@systematic-debugging`
- `@verification-before-completion`

---

### Task 1: Add template routing types and conservative fuzzy command matcher

**Files:**
- Modify: `service/src/voice_text_organizer/policy.py`
- Create: `service/tests/test_template_policy.py`

**Step 1: Write the failing tests**

```python
from voice_text_organizer.policy import match_explicit_template_command


def test_meeting_template_requires_action_and_template_tokens() -> None:
    assert match_explicit_template_command("请按会议纪要整理") == "meeting_minutes"
    assert match_explicit_template_command("会议内容很多") is None


def test_task_template_allows_fuzzy_variants_but_not_ambiguous() -> None:
    assert match_explicit_template_command("帮我列个任务清单") == "task_list"
    assert match_explicit_template_command("列一下") is None


def test_translation_template_command_case_insensitive() -> None:
    assert match_explicit_template_command("please translate to chinese") == "translation"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest service/tests/test_template_policy.py -q`  
Expected: FAIL with missing function or wrong behavior.

**Step 3: Write minimal implementation**

```python
TemplateName = Literal["light_edit", "meeting_minutes", "task_list", "translation"]

def match_explicit_template_command(voice_text: str) -> TemplateName | None:
    normalized = _normalize_command(voice_text)
    if _has_action_token(normalized) and _has_meeting_token(normalized):
        return "meeting_minutes"
    if _has_action_token(normalized) and _has_task_token(normalized):
        return "task_list"
    if _has_translation_action(normalized) and _has_translation_target(normalized):
        return "translation"
    return None
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest service/tests/test_template_policy.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/policy.py service/tests/test_template_policy.py
git commit -m "feat: add conservative fuzzy template command matcher"
```

---

### Task 2: Add classifier contract and threshold decision helper

**Files:**
- Create: `service/src/voice_text_organizer/template_classifier.py`
- Modify: `service/src/voice_text_organizer/policy.py`
- Create: `service/tests/test_template_classifier.py`

**Step 1: Write the failing tests**

```python
from voice_text_organizer.policy import decide_template_from_classifier


def test_low_confidence_falls_back_to_light_edit() -> None:
    decision = decide_template_from_classifier(
        predicted_template="meeting_minutes",
        confidence=0.61,
        threshold=0.72,
    )
    assert decision.template == "light_edit"
    assert decision.decision_type == "low_confidence_fallback_light"


def test_high_confidence_uses_predicted_template() -> None:
    decision = decide_template_from_classifier(
        predicted_template="task_list",
        confidence=0.88,
        threshold=0.72,
    )
    assert decision.template == "task_list"
    assert decision.decision_type == "auto_template"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest service/tests/test_template_classifier.py -q`  
Expected: FAIL due to missing decision helper/types.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class TemplateDecision:
    template: TemplateName
    decision_type: str
    confidence: float | None = None
    reason: str | None = None

def decide_template_from_classifier(...):
    if confidence < threshold:
        return TemplateDecision("light_edit", "low_confidence_fallback_light", confidence, reason)
    return TemplateDecision(predicted_template, "auto_template", confidence, reason)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest service/tests/test_template_classifier.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/template_classifier.py service/src/voice_text_organizer/policy.py service/tests/test_template_classifier.py
git commit -m "feat: add classifier threshold decision contract"
```

---

### Task 3: Add template-aware prompt builder

**Files:**
- Modify: `service/src/voice_text_organizer/rewrite.py`
- Create: `service/tests/test_rewrite_template_prompt.py`

**Step 1: Write the failing tests**

```python
from voice_text_organizer.rewrite import build_template_prompt


def test_light_edit_prompt_does_not_force_fixed_sections() -> None:
    messages = build_template_prompt("口头描述", template="light_edit")
    assert "Do not force rigid section templates" in messages[0]["content"]


def test_meeting_prompt_contains_minutes_sections() -> None:
    messages = build_template_prompt("今天讨论发布计划", template="meeting_minutes")
    assert "Topic" in messages[1]["content"]
    assert "Action Items" in messages[1]["content"]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest service/tests/test_rewrite_template_prompt.py -q`  
Expected: FAIL due to missing function/instructions.

**Step 3: Write minimal implementation**

```python
def build_template_prompt(voice_text: str, *, template: str, selected_text: str | None = None, existing_text: str | None = None) -> list[dict[str, str]]:
    # Keep selected text translation branch behavior unchanged.
    # Build template-specific system/user instructions for light_edit, meeting_minutes, task_list, translation.
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest service/tests/test_rewrite_template_prompt.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/rewrite.py service/tests/test_rewrite_template_prompt.py
git commit -m "feat: add template-aware rewrite prompt builder"
```

---

### Task 4: Integrate routing flow into session/record endpoints with fallback and logs

**Files:**
- Modify: `service/src/voice_text_organizer/main.py`
- Modify: `service/tests/test_session_api.py`
- Modify: `service/tests/test_record_api.py`

**Step 1: Write failing API tests for new routing behavior**

```python
def test_session_stop_low_confidence_falls_back_light_edit(...):
    # classifier returns confidence below threshold
    # assert final_text comes from light_edit path

def test_record_stop_explicit_meeting_command_uses_meeting_template(...):
    # assert chosen template route uses meeting prompt path
```

**Step 2: Run tests to verify they fail**

Run:
- `python -m pytest service/tests/test_session_api.py -q`
- `python -m pytest service/tests/test_record_api.py -q`  
Expected: FAIL before routing integration.

**Step 3: Implement minimal endpoint integration**

```python
# Flow in both endpoints:
# 1) selected-text translation override
# 2) explicit template command
# 3) classifier + threshold
# 4) build_template_prompt + route_rewrite
# 5) on exception -> light_edit fallback
# 6) log decision_type/template/confidence
```

**Step 4: Run tests to verify pass**

Run:
- `python -m pytest service/tests/test_session_api.py -q`
- `python -m pytest service/tests/test_record_api.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/main.py service/tests/test_session_api.py service/tests/test_record_api.py
git commit -m "feat: wire adaptive template routing into stop endpoints"
```

---

### Task 5: Add threshold config and settings surface

**Files:**
- Modify: `service/src/voice_text_organizer/config.py`
- Modify: `service/src/voice_text_organizer/schemas.py`
- Modify: `service/src/voice_text_organizer/main.py`
- Modify: `service/tests/test_settings_api.py`

**Step 1: Write failing tests**

```python
def test_settings_exposes_template_threshold(client):
    response = client.get("/v1/settings")
    assert "auto_template_confidence_threshold" in response.json()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest service/tests/test_settings_api.py -q`  
Expected: FAIL because field is missing.

**Step 3: Implement minimal settings support**

```python
class Settings(BaseModel):
    auto_template_confidence_threshold: float = 0.72

class SettingsViewResponse(BaseModel):
    auto_template_confidence_threshold: float

class SettingsUpdateRequest(BaseModel):
    auto_template_confidence_threshold: float | None = None
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest service/tests/test_settings_api.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add service/src/voice_text_organizer/config.py service/src/voice_text_organizer/schemas.py service/src/voice_text_organizer/main.py service/tests/test_settings_api.py
git commit -m "feat: expose auto-template threshold in runtime settings"
```

---

### Task 6: Documentation and full verification

**Files:**
- Modify: `README.md`

**Step 1: Update docs**

Document:
- supported templates (`light_edit`, `meeting_minutes`, `task_list`, `translation`)
- low-confidence fallback to `light_edit`
- explicit command priority and conservative fuzzy matching

**Step 2: Run full test suite**

Run: `python -m pytest service/tests -q`  
Expected: all tests PASS.

**Step 3: Optional manual smoke**

Run:
- `start-app.cmd`
- validate:
  - casual speech -> `light_edit`
  - explicit "会议纪要" command -> minutes structure
  - explicit "任务清单" command -> action list
  - selected text + translation command -> translation output

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: describe adaptive template routing behavior"
```

**Step 5: Final verification**

Run:
- `git status --short`
- `python -m pytest service/tests -q`

Expected:
- clean working tree
- all tests PASS
