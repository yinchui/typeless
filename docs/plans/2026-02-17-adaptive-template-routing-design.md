# Adaptive Template Routing Design

Date: 2026-02-17  
Status: Approved

## 1. Context and Goal

The current product is transcription-first, but output style is still too rigid for production use.  
Users want flexible formatting:

- If speech has real structure, the system should generate structured notes.
- If speech is casual spoken content, it should not force a fixed 3-section template.
- Translation for selected text must stay reliable.

Primary goal:
- Deliver adaptive template routing with safe fallback behavior, while keeping transcription usability first.

## 2. Final Product Decisions

User-approved decisions:

1. Routing strategy: hybrid router (rules + classifier).
2. Low confidence behavior: fallback directly to base output.
3. Base output: `light_edit` (plain readable text with paragraphing).
4. Explicit template voice command: absolute priority.
5. Public template set (v1):
   - `light_edit`
   - `meeting_minutes`
   - `task_list`
   - `translation`
6. Command matching style: robust fuzzy matching, but conservative:
   - Must hit both action keyword and template keyword.
   - Ambiguous phrases must not force template execution.

## 3. Routing Architecture

Unified flow for both `/v1/session/stop` and `/v1/record/stop`:

1. Normalize ASR text.
2. If selected text exists and translation command is recognized, route to selected-text translation branch first.
3. Run explicit command matcher (fuzzy, conservative).
4. If explicit command matched: use that template directly.
5. If not matched: run template classifier and produce:
   - `template`
   - `confidence`
   - `reason`
6. If `confidence < auto_template_confidence_threshold`: route to `light_edit`.
7. If `confidence >= threshold`: auto-apply predicted template.
8. If template execution fails at runtime: fallback to `light_edit`.

## 4. Decision Types and Observability

Add explicit decision labels for logs and metrics:

- `selected_translation_rewrite`
- `explicit_template`
- `auto_template`
- `low_confidence_fallback_light`
- `template_error_fallback_light`

Per request logs should include:

- endpoint
- decision type
- chosen template
- confidence (if classifier path)
- fallback flag
- failure stage (if any)

## 5. Template Output Contracts (v1)

### `light_edit` (base output)
- Keep original meaning and key details.
- Remove obvious filler and improve punctuation/paragraph boundaries.
- Do not force heading blocks or rigid formats.

### `meeting_minutes`
- Structured sections: `Topic`, `Key Discussion`, `Decisions`, `Action Items`.
- Omit sections that are not present in source speech.
- Never fabricate missing facts.

### `task_list`
- Output actionable items.
- Prefer extraction fields: action, object, time (if present), owner (if present).
- Unknown fields remain empty; no guessing.

### `translation`
- Translation only, no summarization or expansion.
- Keep terms, numbers, and list structure when possible.
- For selected-text scenario, selected text remains highest-priority input.

## 6. Fuzzy Command Matching (Conservative)

Principles:

- Support synonyms, spoken variants, and small recognition noise.
- Require dual-hit to reduce false triggers:
  - Action intent token (for example: convert/organize/translate/list)
  - Template intent token (for example: meeting/task/translate/note)
- If only one side is detected or meaning is unclear, do not direct-route by command.
- In unclear cases, continue to classifier path.

## 7. Config and Runtime Control

Introduce runtime config:

- `auto_template_confidence_threshold` (default `0.72`)

Operational requirements:

- Threshold can be tuned without protocol changes.
- Command lexicon for fuzzy match should be centrally defined and test-covered.
- Existing API schema between agent and backend stays unchanged.

## 8. Testing and Rollout

Test layers:

1. Unit tests:
   - fuzzy command dual-hit behavior
   - classifier threshold routing
   - low-confidence fallback to `light_edit`
2. API tests:
   - `/v1/session/stop` and `/v1/record/stop` parity
   - explicit command routes correctly
   - runtime template errors fallback to `light_edit`
3. Regression tests:
   - selected-text translation flow remains stable

Rollout:

1. Feature-flagged internal rollout first.
2. Observe decision metrics and fallback/error rates.
3. Tune threshold/lexicon, then make default-on.

## 9. Non-goals (v1)

- No hard-coded single output template for all utterances.
- No mandatory user-facing mode switch UI in this iteration.
- No agent-backend protocol change.
