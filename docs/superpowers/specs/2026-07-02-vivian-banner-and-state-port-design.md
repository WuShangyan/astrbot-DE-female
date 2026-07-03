# Vivian Vale · Banner & State Port Design

> Design doc for porting ASCII-frame banners + JSON state persistence + state-transition banners from `docs/plan/2026-07-01-astrbot-vivian-vale-plugin.md` (the v3-era plan) into the current AstrBot v4 codebase, **without reverting any v3→v4 migration work**.

**Goal:** Replace the current English `✦ 24 voices awakened...` / `✧ The voices fall silent...` strings with full ASCII-frame banners (open / close / clear / haze / voice-bleed), and persist conversation state to a JSON file so the bot survives AstrBot restarts and updates.

**Architecture:** Three files change. `banners.py` is rewritten to provide five banner functions + shared frame constants. `state.py` adds JSON file I/O with a per-instance path and a `threading.Lock` to make `set_*` writes atomic. `main.py` is rewired to call the new banner functions, read/write state via the new JSON-backed `StateStore`, and emit clear/haze banners on direction transitions.

**Tech stack:** Python 3.10+, AstrBot v4 (current), no new dependencies. Smoke tests stay as `if __name__ == "__main__":` blocks (existing convention; no pytest).

---

## Scope

### In scope

- ASCII-frame banner format for toggle on/off (replaces English strings)
- Per-conversation state persisted to `state.json` (currently in-memory only)
- State-transition banners (clear/haze) fired on direction changes
- Voice-bleed banner restructured to take `(skill_name, sample_line, body_line)` and emit a 4-line framed block
- `state.py` gets a `threading.Lock` to make `set_*` writes atomic (the existing in-memory version has no lock)
- `.gitignore` updated to ignore the runtime `state.json`

### Out of scope

- Reverting any v3→v4 migration (no `@register_star`, no `dispose`, `VivianVale` class name stays, `metadata.yaml` v4 fields stay)
- Changing the 24-skill set (the plan describes 12 skills; the current repo has 24 and stays at 24 — `epigraphs.SKILL_EPIGRAPHS` is already populated for 24 entries)
- Changing `persona_base.md` / `persona_de.md` content
- Refactoring voice-bleed LLM prompt into a 3-tuple return (out of scope — see §5 for the deferred work item)
- Adding pytest infrastructure

### Assumed unchanged

- `epigraphs.py` — already provides `OPENING_EPIGRAPH` (复仇女神 quote) and `SKILL_EPIGRAPHS` (24 entries, 12-space indented). No changes.
- `parsing.py` — pure helpers, no changes.
- `skills/*/SKILL.md` (24 dirs) — no changes.

---

## 1. Architecture

### Runtime data flow

```
AstrBot plugin load
    │
    ├─ initialize()
    │      ├─ StateStore(plugin_dir / "state.json")   ← loads JSON (or empty default if missing/corrupt)
    │      ├─ load persona files
    │      ├─ load 24 skill bodies
    │      └─ build _de_system_prompt
    │
    ├─ User sends message (AstrBot event)
    │
    ├─ on_message (priority=1)
    │      ├─ sleep-window auto-close
    │      ├─ group @-filter
    │      ├─ direction inference (calls state.get_direction)
    │      └─ voice-bleed (DE OFF): can_voice_bleed → render_voice_bleed_banner
    │
    ├─ inject_persona (on_llm_request)
    │      └─ if state.is_open(conv_id): append _de_system_prompt + dynamic parts
    │
    ├─ LLM call
    │
    ├─ on_response (on_llm_response)
    │      ├─ extract_skill_name(resp) → state.set_last_skill(conv_id, name)  ← JSON write
    │      ├─ extract_outcome(resp)    → state.record_failure(...)
    │      └─ direction cache update via infer_direction(resp_text)
    │
    └─ on_decorating_result (after LLM, before user sees reply)
           ├─ identity scrub + length cap
           └─ direction transition check → event.send(render_clear_banner | render_haze_banner)
```

### File-level change summary

| File | Action | Lines (approx) |
|------|--------|---------------|
| `banners.py` | Rewrite | ~150 |
| `state.py` | Add JSON I/O + lock + `last_skill` API | +60 / -0 |
| `main.py` | Update calls + new wiring | +30 / -10 |
| `.gitignore` | Add `state.json` | +1 |
| `docs/CLAUDE.md` | Update banners section + state.json note | +5 |

---

## 2. Components

### 2.1 `banners.py` (rewrite)

**Module-level constants:**

```python
_TOP_BAR = "░▒▓" + "█" * 66 + "▓▒░"
_DIVIDER = "-" * 72

_OPEN_STATUS = "  >>> 二十四个声音正在门后争吵... 黑暗里有什么正在涌动..."
_CLOSE_STATUS = "  >>> 舞台灯光熄灭。幕布落下。声音们沉沉睡去..."
```

**State-transition banner bodies** (固定引文,不查 epigraph 表):

```python
_CLEAR_BANNER_BODY = (
    "            凌晨三点点的那根烟，比任何证词都亮。\n"
    "          清醒的人 — 是看得见黑影的那种。"
)
_CLEAR_BANNER_STATUS = "  >>> 一根烟点亮了——二十四个声音都看见了黑影。"

_HAZE_BANNER_BODY = (
    "            那瓶威士忌见底的时候，镜里只剩影子，没有名字。\n"
    "          醉了的人 — 是连自己都不认识的那几分钟。"
)
_HAZE_BANNER_STATUS = "  >>> 那二十四个声音散成一片雾——谁是谁，全乱了。"
```

**Voice-bleed body lines** (冷淡本体随机抽一条):

```python
_VOICE_BLEED_BODY_LINES: tuple[str, ...] = (
    "她没听见。",
    "她没理。",
    "她回过神。",
    "……走神了。",
    "（压了压帽檐。）",
    "……嗯。",
)
```

**Shared renderer:**

```python
def _render(epigraph_body: str, status_line: str) -> str:
    return (
        f"{_TOP_BAR}\n"
        f"\n"
        f"{epigraph_body}\n"
        f"\n"
        f"{_DIVIDER}\n"
        f"{status_line}\n"
        f"{_TOP_BAR}"
    )
```

**Five public functions:**

| Function | Signature | Behavior |
|----------|-----------|----------|
| `render_open_banner` | `() -> str` | `_render(epigraphs.get_epigraph(None), _OPEN_STATUS)` |
| `render_close_banner` | `(last_skill: str \| None) -> str` | `_render(epigraphs.get_epigraph(last_skill), _CLOSE_STATUS)` |
| `render_clear_banner` | `() -> str` | `_render(_CLEAR_BANNER_BODY, _CLEAR_BANNER_STATUS)` |
| `render_haze_banner` | `() -> str` | `_render(_HAZE_BANNER_BODY, _HAZE_BANNER_STATUS)` |
| `render_voice_bleed_banner` | `(skill_name: str, sample_line: str, body_line: str) -> str` | `_TOP_BAR + 空行 + "  〔{skill_name}〕{sample_line}" + 空行 + "  {body_line}" + 空行 + _TOP_BAR`,**不带** divider/status/epigraph |

**Preserved:** `render_sleep_banner()` (no change — sleep message stays as-is).

**Removed:** the old `render_toggle_on_banner` / `render_toggle_off_banner` / `render_failure_hint` / `render_force_failure` English strings. (Failure rhythm is now driven entirely by `state.record_failure`; the hint/force blocks go into `extra_user_content_parts` as text, not as separate banner frames. This matches the plan's failure-rhythm template format.)

**Imports:** `from epigraphs import get_epigraph` (already exists).

### 2.2 `state.py` (add JSON I/O + lock + `last_skill` API)

**Constructor change:**

```python
class StateStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path  # None → in-memory only (preserves existing tests)
        self._lock = threading.Lock()
        self._data: dict = {"conversations": {}}
        self._load()
```

`path=None` keeps the existing in-memory smoke tests working unchanged. When `main.py` passes a real `Path`, JSON I/O kicks in.

**JSON load/save:**

```python
def _load(self) -> None:
    if self._path is None:
        return
    if not self._path.exists():
        return
    try:
        raw = self._path.read_text("utf-8")
        if raw.strip():
            self._data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        logger.warning("state.json corrupt/unreadable; using empty default")
        self._data = {"conversations": {}}

def _save(self) -> None:
    if self._path is None:
        return
    try:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning(f"state.json save failed: {e}; state kept in memory only")
```

**Bucket helper (per-conversation):**

```python
def _bucket(self, conv_id: str) -> dict:
    return self._data["conversations"].setdefault(conv_id, {})
```

**New `last_skill` API:**

```python
def get_last_skill(self, conv_id: str) -> str | None:
    with self._lock:
        return self._data["conversations"].get(conv_id, {}).get("last_skill")

def set_last_skill(self, conv_id: str, name: str | None) -> None:
    with self._lock:
        self._bucket(conv_id)["last_skill"] = name
        self._save()
```

**Lock wrapping for existing mutators:** all `set_*` / `record_*` methods gain `with self._lock:` around their state mutation + `_save()`. Read-only methods (`is_*`, `get_*`, `can_*`) also gain the lock (cheap, eliminates TOCTOU risk).

**New module-level import:** `import json`, `import threading`, `import logging`.

**Existing fields preserved unchanged:**
- `de_enabled: bool`
- `de_toggle_ts: float`
- `opened_today: bool`
- `drunk_counter: int`
- `_drunk_timestamps: list[float]`
- `failure_streak: int`
- `_direction_cache: dict[str, Optional[Literal["清", "混"]]]`
- `_voice_bleed_last_ts: float`
- `_voice_bleed_last_skill: str`
- `_silence_bleed_last_ts: float`
- `_last_message_ts: dict[str, float]`

**Existing methods preserved unchanged (signatures + behavior):**
- `touch_drunk`, `is_drunk`, `check_sleep_window`, `maybe_reset_daily`,
  `record_failure`, `should_force_failure`, `should_hint_failure`,
  `get_direction`, `set_direction`, `can_voice_bleed`, `record_voice_bleed`,
  `touch_last_message`, `can_silence_bleed`, `record_silence_bleed`

### 2.3 `main.py` (rewire)

**Imports change:**

```python
# remove:
from .banners import (
    render_toggle_on_banner,
    render_toggle_off_banner,
    render_sleep_banner,
    render_failure_hint,
    render_force_failure,
)
# add:
from .banners import (
    render_open_banner,
    render_close_banner,
    render_clear_banner,
    render_haze_banner,
    render_voice_bleed_banner,
    render_sleep_banner,
)
```

**`initialize()` change:**

```python
self._plugin_dir = Path(__file__).parent
self.state = StateStore(self._plugin_dir / "state.json")
```

**`cmd_open`:**

```python
yield event.plain_result(render_open_banner())
conv_id = event.unified_msg_origin
self.state.set_open(conv_id, True)
```

(`set_open` is a new method on `StateStore` that wraps the existing `de_enabled = True` + `_save()`. For consistency, the existing `self.state.de_enabled = True` direct-write inside `cmd_open` is replaced with the new method call. Same for `cmd_close`. Note: `opened_today: bool` keeps its existing semantics and is still set via `self.state.opened_today = True` directly — see §6 Deferred for the date-string version.)

**`cmd_close`:**

```python
conv_id = event.unified_msg_origin
last_skill = self.state.get_last_skill(conv_id)
yield event.plain_result(render_close_banner(last_skill))
self.state.set_open(conv_id, False)
```

**Sleep auto-close (inside `on_message`):** same as today — `self.state.de_enabled = False` becomes `self.state.set_open(conv_id, False)`.

**`on_response` additions:**

```python
skill_name = extract_skill_name(resp_text)
if skill_name:
    self.state.set_last_skill(conv_id, skill_name)
```

**`on_decorating_result` direction transition:**

```python
# after the existing identity scrub + length cap loop:
conv_id = event.unified_msg_origin
prev_direction = self.state._direction_cache.get(conv_id)  # read-only peek
curr_direction = infer_direction(...)  # or reuse cached from on_message
# if transition (None → 清, None → 混, 清 ↔ 混), emit banner via event.send
if curr_direction and curr_direction != prev_direction:
    banner = render_clear_banner() if curr_direction == "清" else render_haze_banner()
    try:
        await event.send(event.plain_result(banner))
    except Exception:
        pass  # never block the main reply
```

(Note: `prev_direction` capture is best-effort — if the cache was just updated in `on_message`, we read the value before the LLM call. If the LLM response itself flips direction, the transition banner reflects the response's direction, not the user's. This matches the plan's "first time entering [清]/[混] state" semantics.)

**Voice-bleed path (inside `on_message`):** the existing `_generate_voice_bleed` returns a single line of text. That return path stays — voice-bleed keeps its current single-line behavior. **The plan's 3-arg `(skill_name, sample_line, body_line)` signature is documented but not wired in this round; see §5 Deferred.**

### 2.4 `.gitignore`

Add one line:

```
# AstrBot runtime state (generated by plugin)
state.json
```

(`docs/plan/2026-07-01-...md` already covered this in its Task 1 template; we adopt the same convention.)

### 2.5 `docs/CLAUDE.md`

Update two sentences in the existing narrative:

- Banner section: replace "ASCII 框线 banner" hand-waving with concrete references to `render_open_banner` / `render_close_banner` / `render_clear_banner` / `render_haze_banner` / `render_voice_bleed_banner`.
- Add one line: "State persisted to `state.json` in the plugin directory; reload-safe across AstrBot restarts and updates."

(CLAUDE.md is descriptive, not code; tracked in §4 "Out of scope" as documentation cleanup only.)

---

## 3. Data Flow

### JSON shape on disk

```json
{
  "conversations": {
    "aiocqhttp:GroupMessage:123456789": {
      "open": true,
      "opened_today": true,
      "de_toggle_ts": 1751411500.0,
      "last_skill": "通情达理",
      "drunk_count": 2,
      "last_drink_at": 1751412000.0,
      "_drunk_timestamps": [1751411800.0, 1751411900.0, 1751412000.0],
      "failure_streak": 3,
      "direction_cache": {"aiocqhttp:GroupMessage:123456789": "清"},
      "voice_bleed_last_ts": 1751410000.0,
      "voice_bleed_last_skill": "食髓知味",
      "silence_bleed_last_ts": 0.0,
      "last_message_ts": {"aiocqhttp:GroupMessage:123456789": 1751412500.0}
    }
  }
}
```

Field shapes mirror the dataclass fields exactly. `opened_today` stays as a `bool` (existing behavior preserved — resets at 08:00 via `maybe_reset_daily`). The date-string version `opened_today_date` and the wake-tracking field `was_asleep_last_check` are **deferred** to §6.

### Lifecycle invariants

- **One `set_*` per state transition.** Methods are not called speculatively — each `set_open` / `set_last_skill` / `record_failure` corresponds to one observable event (toggle, response, drink trigger).
- **`_save()` runs synchronously after every mutation.** Disk writes are tiny (per-conversation JSON, ~500 bytes), so no batching is needed. This keeps the "state survives reload" promise simple.
- **State changes are thread-safe.** All mutations under `self._lock`; reads too (cheap, eliminates TOCTOU between `is_open` and the subsequent `set_open` in a race).
- **JSON failure is non-fatal.** Corrupt file → empty default; write failure → log + continue in memory. Plugin never crashes on state I/O.

---

## 4. Error handling

| Failure | Behavior | Impact |
|---------|----------|--------|
| `state.json` missing on first load | `_load()` returns; data starts empty | First toggle creates the file |
| `state.json` corrupt (bad JSON) | `_load()` catches `JSONDecodeError`, resets to empty default, logs warning | Bot still works; loses prior state |
| `state.json` unreadable (permissions) | `_load()` catches `OSError`, logs warning, runs in-memory | Bot still works for current session; no persistence |
| `state.json` write fails (disk full / perms) | `_save()` catches `OSError`, logs warning | Bot keeps running with in-memory state; next write may succeed |
| `event.send(clear/haze_banner)` fails | `try/except` swallows; main reply unaffected | Banner skipped, message still delivered |
| `epigraphs.get_epigraph(None)` at close time | Falls back to `OPENING_EPIGRAPH` | Close banner shows the 复仇女神 quote instead of skill quote (acceptable fallback) |

No user-facing error states. All failures degrade gracefully.

---

## 5. Testing

Smoke tests stay inline in each module's `if __name__ == "__main__":` block (existing convention; no pytest).

### `python3 banners.py`

Visual + content assertions:

- 5 banner functions each called and printed
- Each banner starts with `_TOP_BAR` and ends with `_TOP_BAR`
- `render_open_banner` contains `"复仇女神"` and `_OPEN_STATUS`
- `render_close_banner("食髓知味")` contains `"醉于酒"` (食髓知味 epigraph) AND NOT `"复仇女神"`
- `render_close_banner(None)` falls back to `"复仇女神"`
- `render_clear_banner` contains `"凌晨三点点的那根烟"` AND NOT `"复仇女神"`
- `render_haze_banner` contains `"威士忌见底"` AND NOT `"复仇女神"`
- `render_voice_bleed_banner("食髓知味", "再点一根。", "她没听见。")`:
  - contains `"食髓知味"`, `"再点一根。"`, `"她没听见。"`
  - contains `_TOP_BAR` (twice)
  - does NOT contain `"[成功]"`, `"[失败]"`, `_OPEN_STATUS`, `_CLOSE_STATUS`, `"复仇女神"`

### `python3 state.py`

Existing tests pass unchanged (in-memory path with `path=None`). Add 4 new tests:

- `test_set_open_persists_across_instances`: write JSON to `tmp_path/state.json`, construct `StateStore(path)`, set open True, construct a second `StateStore(path)`, assert `is_open` returns True on the second.
- `test_set_last_skill_persists`: same pattern, round-trip `set_last_skill("conv-1", "食髓知味")`.
- `test_corrupt_json_falls_back_to_empty`: write `"not json"` to `tmp_path/state.json`, construct `StateStore(path)`, assert `is_open("any")` is False (no exception).
- `test_missing_json_file_creates_on_first_write`: construct `StateStore(tmp_path / "new.json")`, call `set_open("c1", True)`, assert file exists and contains `"open": true`.

### `python3 main.py`

Does NOT run as a script (no `__main__` block). Same as today.

### Manual verification in docker

After implementation, push and reload the plugin in the running AstrBot container. Verify:

1. `芝麻开门` → ASCII open banner with `░▒▓` frame + `二十四个声音正在门后争吵...`
2. `关门` → ASCII close banner with `二十四个声音沉沉睡去...`
3. Send `晚上好` after opening → reply starts with `[技能名] [成功|失败]` (existing behavior, unaffected)
4. Send `我想点根烟` after opening → `[清]` direction entered → `render_clear_banner` fires as separate message via `event.send`
5. `cat /AstrBot/data/plugins/vivian_vale/state.json` → contains `conversations` dict with the test conv

---

## 6. Open questions / Deferred work

### Deferred (out of scope this round)

- **Voice-bleed 3-tuple refactor.** Plan calls for `_generate_voice_bleed` to return `(skill_name, sample_line, body_line)` so the LLM picks the skill and feeds `render_voice_bleed_banner` directly. Current code returns a single text line. Implementing requires rewriting the voice-bleed LLM prompt to request all three pieces and update the prompt template accordingly. **Tracked as separate work item; not blocking this round.**
- **state.py wake-reset hook.** Plan defines `clear_drunk_state(conv_id)` that resets drunk_count / last_drink_at / direction / failure_streak on wake. Current `on_message` doesn't call it. Requires the `was_asleep_last_check` field and a `set_was_asleep` round-trip — non-trivial enough to defer. **Tracked as separate work item.**
- **`opened_today` → `opened_today_date` migration.** Replace the boolean (resets at 08:00) with a date string (resets when today's date differs from stored date). Better semantics, but a behavior change — defer to a follow-up round so the JSON-port PR stays focused.
- **pytest.** Plan uses pytest. Repo uses inline smoke tests. **Stay with smoke tests for now** (matches the rest of the repo; no test runner means no CI).

### Risks

- **Lock contention.** `threading.Lock` is per-instance. AstrBot's event loop may run multiple async handlers concurrently; the lock is only held during `_save()` (microseconds), so contention is theoretical, not practical.
- **JSON file size growth.** Each `set_*` rewrites the whole file. With dozens of conversations and frequent updates, the file grows and rewrites get slower. **Acceptable for single-user scenarios** (the typical Vivian Vale user has 1–5 active conversations). If scale becomes a concern, switch to append-only NDJSON or SQLite in a future iteration.

---

## 7. Acceptance criteria

This round is done when:

- [ ] `python3 banners.py` exits 0
- [ ] `python3 state.py` exits 0 (existing tests + 4 new JSON round-trip tests)
- [ ] `python3 parsing.py` exits 0 (unchanged, sanity)
- [ ] `python3 epigraphs.py` exits 0 (unchanged, sanity) — if it has a `__main__` block; otherwise skip
- [ ] `.gitignore` contains `state.json`
- [ ] `state.json` does not appear in `git status` after a test toggle
- [ ] Docker reload shows ASCII banners as expected
- [ ] Direction transition fires clear/haze banner (verified by sending `点根烟` in DE mode)
- [ ] One commit pushed to `WuShangyan/astrbot-DE-female`