# Vivian Vale · Wake Reset + Auto-Close Banner + Voice-Bleed 3-Tuple Design

> Design doc for the **second port round** of the Vivian Vale AstrBot plugin. Addresses four spec gaps identified after the first port (commit `5584569`): wake hard-reset, sleep auto-close banner fix, voice-bleed 3-tuple refactor, and manual close failure_streak reset. Carries forward all v3→v4 migration work intact.

**Goal:** Bring the implementation into strict alignment with `docs/specs/2026-06-30-astrbot-disco-voices-plugin-design.md` §4.4.2 (wake hard-reset), §4.4.7a (auto-close uses `render_close_banner`), §4.4.7b (voice-bleed 3-tuple frame), and §4.3 (manual close resets `failure_streak`). All four changes preserve AstrBot v4 compatibility — no API changes, no Python identifier renames, no `metadata.yaml` churn.

**Architecture:** Two files change. `state.py` gains one dataclass field (`was_asleep_last_check: dict[str, bool]`) and three new methods (`get_was_asleep` / `set_was_asleep` / `clear_drunk_state` / `clear_full_session`); `_save`/`_load` extend their flat JSON shape. `main.py` adds transition detection at the top of `on_message`, swaps the sleep-window block's banner yield, refactors `_generate_voice_bleed` to return `(skill, sample, body)`, and adds `failure_streak = 0 + _save()` to `cmd_close`.

**Tech stack:** Python 3.10+, AstrBot v4, stdlib only (`json` already imported for parsing). Smoke tests stay inline as `if __name__ == "__main__":` blocks. No pytest, no config schema changes, no `metadata.yaml` updates.

---

## Scope

### In scope

- **§4.4.2 Wake hard-reset** — `clear_drunk_state(conv_id)` method on `StateStore`; called from `on_message` on `was_asleep → is_awake` transition. Resets `drunk_count=0`, `last_drink_at=None`, `failure_streak=0` (§4.3 cross-reference).
- **§4.4.7a Sleep auto-close banner fix** — sleep-window auto-close yields `render_close_banner(last_skill)` (not `render_sleep_banner()`), then clears the 5-field session state. Triggered once on `is_awake → is_asleep` transition while `de_enabled=True`.
- **§4.4.7b Voice-bleed 3-tuple refactor** — `_generate_voice_bleed` returns `(skill_name, sample_line, body_line)` instead of a single text line. Skill and body_line picked by code (random, with anti-repeat). LLM generates only `sample_line` (one short utterance). Output rendered via `render_voice_bleed_banner(skill_name, sample_line, body_line)`.
- **§4.3 Manual close reset** — `cmd_close` sets `failure_streak = 0` directly + calls `_save()` (no new method; one field only).
- **`was_asleep_last_check` field** — per-conversation bool, JSON-persisted, used to drive transition detection. New field in the flat JSON shape.

### Out of scope

- New AstrBot v4 APIs (none needed; all changes use existing hooks).
- `metadata.yaml` / `plugin.json` / `plugin.json` updates (AstrBot discovery unchanged).
- `enabled_skills` config schema (P2 item from the previous round's review — deferred).
- Format-mismatch post-processing on LLM output (P3 — deferred).
- `is_at_me` aiocqhttp fast-path (P3 — deferred).
- Thought Cabinet / multi-character / dice rolls (out of scope per original spec §14).
- `persona_base.md` / `persona_de.md` content changes.

### Assumed unchanged

- `banners.py` — all five banner functions stay as they are after the first port; `render_close_banner(last_skill)` already accepts the optional-skill argument, `render_voice_bleed_banner(skill, sample, body)` already takes three strings.
- `epigraphs.py` — `SKILL_EPIGRAPHS` dict already has 24 entries.
- `parsing.py` — pure helpers unchanged.
- 24-skill set preserved.

---

## 1. Architecture

### State machine addition

The existing `on_message` flow treats each message independently with respect to sleep. The new design adds a **transition detector** at the top:

```
on_message(event):
    now = datetime.now()
    conv_id = event.unified_msg_origin
    is_sleep_now = state.check_sleep_window(now.hour)
    was_asleep = state.get_was_asleep(conv_id)

    # --- Transition: wake → sleep (first message in new sleep cycle) ---
    if (not was_asleep) and is_sleep_now:
        if state.de_enabled:
            last_skill = state.get_last_skill(conv_id)
            state.set_open(conv_id, False)
            state.clear_full_session(conv_id)
            yield plain_result(render_close_banner(last_skill))
        state.set_was_asleep(conv_id, True)
        return  # no further processing this turn (she's asleep now)

    # --- Transition: sleep → wake (first message in new wake cycle) ---
    if was_asleep and (not is_sleep_now):
        state.clear_drunk_state(conv_id)
        state.set_was_asleep(conv_id, False)
        # do not yield; fall through to normal wake-time processing

    # --- Existing flow (re-ordered: daily reset, sleep-window block, etc.) ---
    state.maybe_reset_daily(now.hour)

    # Sleep-window block: still emits sleep_banner for messages arriving
    # *during* the sleep window after the transition banner already fired.
    if is_sleep_now:
        if state.de_enabled:
            state.set_open(conv_id, False)
        yield plain_result(render_sleep_banner())
        return

    # --- Normal wake-time processing ---
    if event.get_group_id() and not _is_at_me(event):
        return
    state.touch_last_message(conv_id)
    direction = infer_direction(event.message_str or "")
    if direction:
        state.set_direction(conv_id, direction)
        state.touch_drunk(direction)
    if (not state.de_enabled) and _should_voice_bleed():
        triple = await _generate_voice_bleed(event)
        if triple:
            yield plain_result(render_voice_bleed_banner(*triple))
```

### File-level change summary

| File | Action | Approx lines |
|------|--------|--------------|
| `state.py` | Add field + 4 methods + extend `_save`/`_load` | +60 |
| `main.py` | on_message transition detector + sleep-window block fix + voice-bleed refactor + cmd_close 1-line add | +30 / -10 |
| smoke tests | 3 new tests in `state.py` `__main__` block | +50 |

---

## 2. Components

### 2.1 `state.py` — new field + methods

**Field** (added to dataclass body, 13th field after `_last_skill`):

```python
was_asleep_last_check: dict[str, bool] = field(default_factory=dict)
```

**Extend `_save`** (add one key):

```python
state = {
    # ... existing 11 keys ...
    "_last_skill": dict(self._last_skill),
    "was_asleep_last_check": dict(self.was_asleep_last_check),  # NEW
}
```

**Extend `_load`** (add one assignment):

```python
self._last_skill = data.get("_last_skill", {})
self.was_asleep_last_check = data.get("was_asleep_last_check", {})  # NEW
```

**Four new methods** (added after `set_last_skill`):

```python
def get_was_asleep(self, conv_id: str) -> bool:
    """Whether the previous message in this conversation arrived during
    the sleep window. Used by `on_message` to detect wake/sleep transitions."""
    with self._lock:
        return self.was_asleep_last_check.get(conv_id, False)


def set_was_asleep(self, conv_id: str, was_asleep: bool) -> None:
    """Update the per-conv sleep-edge flag. Persists to JSON."""
    with self._lock:
        self.was_asleep_last_check[conv_id] = was_asleep
        self._save()


def clear_drunk_state(self, conv_id: str) -> None:
    """Wake hard-reset (§4.4.2 + §4.3 cross-reference): drunk_count=0,
    last_drink_at=None, failure_streak=0. Per-conversation; does NOT
    touch last_skill / last_direction_seen (those survive sleep per spec)."""
    with self._lock:
        d = self._bucket(conv_id)
        d["drunk_count"] = 0
        d["last_drink_at"] = None
        d["failure_streak"] = 0
        self._save()


def clear_full_session(self, conv_id: str) -> None:
    """§4.4.7a auto-close cleanup: clears 5 fields so the next DE session
    starts fresh. last_skill=None, drunk_count=0, last_drink_at=None,
    last_direction_seen=None, failure_streak=0."""
    with self._lock:
        d = self._bucket(conv_id)
        d["last_skill"] = None
        d["drunk_count"] = 0
        d["last_drink_at"] = None
        d["last_direction_seen"] = None
        d["failure_streak"] = 0
        self._save()
```

### 2.2 `main.py` — transition detector + 4 hooks

#### A. `on_message` — replace the existing top-of-function block

The existing function starts with `maybe_reset_daily` then the sleep-window block. Replace the top portion (before the group `@`-filter) with the transition detector.

**Find this existing block:**
```python
async def on_message(self, event: AstrMessageEvent):
    now = datetime.datetime.now()
    self.state.maybe_reset_daily(now.hour)

    # ── 物理层: 睡眠窗口自动关闭 DE ──
    if self.state.check_sleep_window(now.hour) and self.state.de_enabled:
        ...
        yield event.plain_result(render_sleep_banner())
        return
```

**Replace with:**
```python
async def on_message(self, event: AstrMessageEvent):
    now = datetime.datetime.now()
    hour = now.hour
    conv_id = event.unified_msg_origin
    is_sleep_now = self.state.check_sleep_window(hour)
    was_asleep = self.state.get_was_asleep(conv_id)

    # ── 醒→睡 转换:首次进入睡眠窗口时自动收摊 ──
    if (not was_asleep) and is_sleep_now:
        if self.state.de_enabled:
            last_skill = self.state.get_last_skill(conv_id)
            self.state.set_open(conv_id, False)
            self.state.clear_full_session(conv_id)
            yield event.plain_result(render_close_banner(last_skill))
        self.state.set_was_asleep(conv_id, True)
        return  # auto-close banner already conveyed "she's asleep"

    # ── 睡→醒 转换:首条醒来消息静默 reset drunk 相关状态 ──
    if was_asleep and (not is_sleep_now):
        self.state.clear_drunk_state(conv_id)
        self.state.set_was_asleep(conv_id, False)
        # fall through to normal wake-time processing

    self.state.maybe_reset_daily(hour)

    # ── 仍在睡眠窗口:任何后续消息都 yield sleep_banner ──
    if is_sleep_now:
        if self.state.de_enabled:
            # 防御性:若 was_asleep 状态因 reload 缺失导致漏掉了 auto-close
            self.state.set_open(conv_id, False)
        yield event.plain_result(render_sleep_banner())
        return
```

#### B. `cmd_close` — add one line after `set_open(False, ...)` (§4.3 strict)

**Find:**
```python
@filter.command("关门")
async def cmd_close(self, event: AstrMessageEvent):
    conv_id = event.unified_msg_origin
    last_skill = self.state.get_last_skill(conv_id)
    self.state.set_open(conv_id, False)
    yield event.plain_result(render_close_banner(last_skill))
```

**Replace with:**
```python
@filter.command("关门")
async def cmd_close(self, event: AstrMessageEvent):
    conv_id = event.unified_msg_origin
    last_skill = self.state.get_last_skill(conv_id)
    self.state.set_open(conv_id, False)
    self.state.failure_streak = 0  # §4.3:芝麻关门清零 failure_streak
    self.state._save()              # 立即持久化(单字段写)
    yield event.plain_result(render_close_banner(last_skill))
```

#### C. `_generate_voice_bleed` — refactor to 3-tuple

**Find the existing implementation** (returns a string):

```python
async def _generate_voice_bleed(self, event: AstrMessageEvent) -> str | None:
    # 调 LLM 生成一段与上下文相关的技能独白,不显示技能名
    # ... returns completion_text or None
```

**Replace with** (returns 3-tuple):

```python
async def _generate_voice_bleed(self, event: AstrMessageEvent) -> tuple[str, str, str] | None:
    """Voice-bleed: code picks skill_name and body_line; LLM only writes
    the sample_line (one short utterance matching the chosen skill's voice).

    Returns (skill_name, sample_line, body_line) or None on any failure.
    Caller passes the tuple to render_voice_bleed_banner(...).
    """
    # 1. Code-side: pick a skill (random, excluding last voice-bleed skill)
    exclude = self.state._voice_bleed_last_skill
    candidates = [k for k in SKILL_EPIGRAPHS if k != exclude]
    if not candidates:
        candidates = list(SKILL_EPIGRAPHS.keys())
    skill_name = random.choice(candidates)

    # 2. Code-side: pick a Vivian reaction line
    body_line = random.choice(_VOICE_BLEED_BODY_LINES)

    # 3. LLM-side: write the skill's whisper (one sentence)
    skill_desc = epigraphs.SKILL_EPIGRAPHS.get(skill_name, "")
    prompt = (
        "你是 Vivian Vale,失忆硬汉女警探。DE 模式关闭时,脑子里偶尔会有一个声音漏出来。\n"
        f"现在漏出的声音来自技能「{skill_name}」——这个声音的内核是:\n"
        f"{skill_desc.strip()}\n\n"
        "用这个技能的口吻,写一句 8-30 字的脑内独白(用'你'称呼用户)。\n"
        "输出格式(JSON,严格): {\"sample\": \"<你的独白>\"}\n"
        "不要加任何解释、标签、或额外文字。"
    )

    try:
        response = await self._ctx.send_llm(
            prompt=prompt,
            system_prompt=self._persona_base,
        )
        text = response.completion_text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.strip("`").lstrip("json").strip()
        data = json.loads(text)
        sample_line = data["sample"].strip()
        if sample_line:
            self.state.record_voice_bleed(skill_name)
            return (skill_name, sample_line, body_line)
    except Exception:
        pass
    return None
```

**Add import at the top of `main.py`** if not present:

```python
import json
```

#### D. voice-bleed gate — update the caller

**Find the existing call site in `on_message`:**

```python
if not self.state.de_enabled and self._should_voice_bleed():
    text = await self._generate_voice_bleed(event)
    if text:
        yield event.plain_result(text)
```

**Replace with:**

```python
if not self.state.de_enabled and self._should_voice_bleed():
    triple = await self._generate_voice_bleed(event)
    if triple:
        skill_name, sample_line, body_line = triple
        yield event.plain_result(
            render_voice_bleed_banner(skill_name, sample_line, body_line)
        )
```

---

## 3. Data Flow

### JSON shape on disk (extended from round 1)

```json
{
  "de_enabled": false,
  "de_toggle_ts": 1751411500.0,
  "opened_today": false,
  "drunk_counter": 0,
  "_drunk_timestamps": [],
  "failure_streak": 0,
  "_direction_cache": {"conv-1": "清"},
  "_voice_bleed_last_ts": 1751410000.0,
  "_voice_bleed_last_skill": "食髓知味",
  "_silence_bleed_last_ts": 0.0,
  "_last_message_ts": {"conv-1": 1751412500.0},
  "_last_skill": {"conv-1": "逻辑思维"},
  "was_asleep_last_check": {"conv-1": false}
}
```

`was_asleep_last_check` is a per-conv bool map. After a wake transition: `{"conv-1": false}`. After entering sleep: `{"conv-1": true}`. On reload: field is restored from JSON.

### Transition state table

| `was_asleep` | `is_sleep_now` | Transition | Action |
|---|---|---|---|
| `False` | `False` | none (steady wake) | normal wake-time flow |
| `True` | `True` | none (steady sleep) | yield `render_sleep_banner`, return |
| `False` | `True` | wake → sleep | if `de_enabled`: auto-close + close banner + `clear_full_session`; set `was_asleep=True`; return |
| `True` | `False` | sleep → wake | `clear_drunk_state`; set `was_asleep=False`; fall through |

Edge case: AstrBot restart during sleep window. `was_asleep_last_check["conv-1"]` is `True` in JSON (from before restart). First post-restart message arrives during sleep → `is_sleep_now=True`. Branch evaluates `(not was_asleep) and is_sleep_now` → False (was_asleep is True). Falls into "steady sleep" branch → yields sleep_banner. ✓

Edge case: AstrBot restart at 7:55. `was_asleep_last_check["conv-1"]` is `True`. First post-restart message arrives at 8:01 → `is_sleep_now=False`. Branch `was_asleep=True, is_sleep_now=False` → triggers wake reset (clears drunk_state). ✓

---

## 4. Error handling

| Failure | Behavior | Impact |
|---------|----------|--------|
| `_save` fails on `clear_drunk_state` / `clear_full_session` / `set_was_asleep` | `logging.warning`; in-memory state still updated; next `_save` may succeed | plugin keeps running |
| LLM returns non-JSON in voice-bleed | `except Exception: pass` returns `None`; no banner emitted this turn | benign; next voice-bleed-eligible message retries |
| LLM JSON has no `sample` key | `KeyError` caught by bare `except`; returns `None` | same as above |
| `last_skill` is `None` at auto-close time | `render_close_banner(None)` falls back to opening epigraph via `epigraphs.get_epigraph(None)` | spec §4.4.7a explicitly allows this fallback |
| `was_asleep_last_check[conv_id]` missing on first message ever | `get_was_asleep` returns `False` (dict.get default) | first message treated as wake, not a transition |

No user-facing error states.

---

## 5. Testing

Smoke tests stay inline in `state.py`'s `__main__` block (existing convention; no pytest).

### New tests in `state.py`

```python
def test_was_asleep_round_trip():
    """was_asleep_last_check survives reload via JSON."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "state.json"
        s1 = StateStore(path)
        s1.set_was_asleep("conv-1", True)
        s2 = StateStore(path)
        assert s2.get_was_asleep("conv-1") is True, "was_asleep persisted"
        s2.set_was_asleep("conv-1", False)
        assert s2.get_was_asleep("conv-1") is False, "was_asleep can be flipped"


def test_clear_drunk_state_resets_3_fields():
    """Wake reset (§4.4.2 + §4.3): drunk_count=0, last_drink_at=None,
    failure_streak=0; other fields (last_skill, direction, last_drink_at
    timestamp list) preserved per spec."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "state.json"
        s = StateStore(path)
        s.set_open("conv-1", True)
        s.touch_drunk("混")
        s.touch_drunk("混")
        s.touch_drunk("混")
        s.record_failure(False)
        s.record_failure(False)  # streak = 2
        s.set_last_skill("conv-1", "通情达理")
        s.set_direction("conv-1", "清")
        # 3 drunk timestamps stored on the timestamps list
        s.clear_drunk_state("conv-1")
        assert s.drunk_counter == 0, "drunk_counter reset"
        assert s.failure_streak == 0, "failure_streak reset (§4.3)"
        assert s.get_last_skill("conv-1") == "通情达理", "last_skill preserved"
        assert s.get_direction("conv-1") == "清", "direction preserved"


def test_clear_full_session_resets_5_fields():
    """Auto-close (§4.4.7a): last_skill=None + drunk_count=0 +
    last_drink_at=None + last_direction_seen=None + failure_streak=0."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "state.json"
        s = StateStore(path)
        s.set_open("conv-1", True)
        s.set_last_skill("conv-1", "逻辑思维")
        s.touch_drunk("混")
        s.set_direction("conv-1", "混")
        s.record_failure(False)
        s.record_failure(False)
        s.clear_full_session("conv-1")
        assert s.get_last_skill("conv-1") is None, "last_skill cleared"
        assert s.drunk_counter == 0, "drunk_counter cleared"
        assert s.get_direction("conv-1") is None, "direction cleared"
        assert s.failure_streak == 0, "failure_streak cleared"


test_was_asleep_round_trip()
test_clear_drunk_state_resets_3_fields()
test_clear_full_session_resets_5_fields()
```

### `main.py` regression check

No automated test for `main.py` (requires AstrBot injection; same constraint as round 1). After implementation:

```bash
python3 state.py       # all 35 existing + 3 new = 38 assertions pass
python3 banners.py     # 31/31 pass (unchanged)
python3 parsing.py     # all pass (unchanged)
```

### Docker end-to-end (user-side, after Task 6 push)

1. Push + reload plugin.
2. Send `芝麻开门` → open banner (unchanged from round 1).
3. Send `晚上好` → DE skill line (unchanged).
4. **New: send `我想点根烟`** → clear banner (unchanged).
5. **New: at 04:00, send a message** → close banner with last-skill epigraph (NOT sleep_banner).
6. **New: at 08:00, send a message** → no banner, but `state.json` shows `failure_streak: 0` for that conv.
7. **New: at noon, send a message with DE OFF** → `voice_bleed_banner(skill, sample, body)` frame appears.

---

## 6. Open questions / Deferred

### Deferred (out of scope this round)

- **`enabled_skills` config schema** (P2 from round 1 review) — would let users opt out of unused skills to save tokens.
- **Format-mismatch post-processing** (P3) — detect when LLM omits the `[技能名] [成功|失败]` line; tolerate silently with a `logging.warning`.
- **`is_at_me` aiocqhttp fast-path** (P3) — `isinstance(event, AiocqhttpMessageEvent)` shortcut.
- **Sleep-window granularity** (P3) — currently auto-closes on any sleep-window message; could be tightened to "first message after wake→sleep transition only" with stricter `was_asleep` semantics.

### Risks

- **`was_asleep_last_check` is per-conversation, not per-plugin-instance.** If two AstrBot workers share the same `state.json` (multi-process deployment), they'd race on this field. The `threading.Lock` is per-instance, so concurrent writes could corrupt the file. **Acceptable for single-instance deployment** (the typical Vivian Vale user runs one AstrBot); multi-process would need a file lock.
- **Voice-bleed JSON output reliability.** Most modern LLMs (Claude, GPT-4+) handle JSON output reliably, but weaker models might add prose around the JSON or use single quotes. The `text.startswith("```")` strip handles markdown fences; bare `except Exception` swallows any other parse failure. Voice-bleed is best-effort; failure is silent (no banner this turn).

---

## 7. Acceptance criteria

This round is done when:

- [ ] `python3 state.py` exits 0 (existing 35 + 3 new = 38 assertions)
- [ ] `python3 banners.py` exits 0 (unchanged)
- [ ] `python3 parsing.py` exits 0 (unchanged)
- [ ] `state.json` round-trip for `was_asleep_last_check` works across reload
- [ ] `cmd_close` sets `failure_streak = 0` and persists
- [ ] First post-sleep message runs `clear_drunk_state` (verified by `state.json` inspection)
- [ ] First wake→sleep message while `de_enabled=True` yields `render_close_banner` (verified by docker)
- [ ] Voice-bleed emits `░▒▓ + 〔技能名〕独白 + 本体一行 + ░▒▓` frame (4 lines, not 1)
- [ ] One commit per logical change (likely 2-3 commits); push to `WuShangyan/astrbot-DE-female`