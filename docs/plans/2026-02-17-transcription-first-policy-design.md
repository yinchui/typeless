# Transcription-First Policy Design

Date: 2026-02-17  
Status: Approved

## 1. Context and Goal

The current voice workflow sometimes rewrites user speech into direct answers instead of returning the spoken question itself.

Primary goal:
- Make the product behave as a transcription tool by default.
- Keep selected-text translation convenience.

User-approved intent:
- No selected text: always output raw transcription (no answering/rewrite).
- Selected text: only allow whitelist commands.
- Selected text + non-whitelist command: output transcription text directly.

## 2. Chosen Approach

Selected approach: backend strategy gateway.

Reason:
- Centralized behavior control in service layer.
- Consistent behavior for all clients.
- Deterministic and testable rules (no prompt-only reliance).

## 3. Behavior Contract

1. No `selected_text`: `final_text = voice_text`.
2. `selected_text` exists and command hits whitelist: run rewrite on selected text.
3. `selected_text` exists and command misses whitelist: `final_text = voice_text`.
4. Empty ASR result: keep existing `no speech detected` error.
5. Whitelist rewrite failure: fallback to `final_text = voice_text`.

## 4. Whitelist Rules (V1)

Apply whitelist only when `selected_text` is non-empty.

Normalization:
- Trim spaces.
- Normalize punctuation.
- Case-insensitive matching for Latin text.

V1 whitelist phrases:
- `翻译成中文` / `翻成中文` / `译成中文` / `英译中`
- `翻译成英文` / `翻成英文` / `译成英文` / `中译英`
- `translate to chinese`
- `translate to english`

Matching:
- Match normalized full command with optional polite wrappers (`请`, `帮我`, etc.).

## 5. Service Data Flow Changes

Affected endpoints:
- `POST /v1/record/stop`
- `POST /v1/session/stop`

Add strategy decision step:
- `decide_processing_mode(voice_text, selected_text, existing_text)`
- Returns:
  - `transcribe_only`
  - `selected_whitelist_rewrite`

Execution:
- `transcribe_only` -> set `final_text` to `voice_text`.
- `selected_whitelist_rewrite` -> build prompt + call rewrite router.

Schema/API compatibility:
- Keep existing request/response schema unchanged.
- Keep AHK client protocol unchanged.

## 6. Error Handling and Fallback

- ASR failure / empty result: unchanged error behavior.
- Rewrite errors in whitelist mode: fallback to transcription text.
- Add debug log fields:
  - `decision_mode`
  - `whitelist_hit`
  - failure stage marker (ASR or rewrite)

## 7. Testing and Acceptance

### Unit tests
- No selected text + question utterance -> no rewrite call; `final_text == voice_text`.
- Selected text + whitelist command -> rewrite path called.
- Selected text + non-whitelist command -> no rewrite call; `final_text == voice_text`.

### API tests
- `record/stop` and `session/stop` both follow the same policy.
- Whitelist + rewrite exception -> fallback to transcription.

### E2E acceptance scenarios
- Ask a question directly: output should be the spoken question text, not an answer.
- Select English text and say "翻译成中文": output should be translated Chinese.
- Select text and give non-whitelist command: output should be transcription text.

Pass criteria:
- Behavior contract satisfied in all scenarios.
- Existing `service/tests` regression suite remains green.

## 8. Non-goals (V1)

- No generic command execution beyond translation whitelist.
- No UI-level mode switch in this design iteration.
- No protocol changes between AHK and backend.
