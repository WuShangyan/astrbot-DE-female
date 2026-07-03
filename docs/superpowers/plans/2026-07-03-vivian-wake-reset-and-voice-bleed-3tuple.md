# Vivian Wake Reset + Voice-Bleed 3-Tuple Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Vivian Vale AstrBot plugin into strict alignment with `docs/specs/2026-06-30-astrbot-disco-voices-plugin-design.md` §4.4.2 (wake hard-reset), §4.4.7a (auto-close yields `render_close_banner`), §4.4.7b (voice-bleed 3-tuple frame), and §4.3 (manual close resets `failure_streak`). All changes preserve AstrBot v4 compatibility.

**Architecture:** Two files change. `state.py` adds one dataclass field (`was_asleep_last_check: dict[str, bool]`) and four new methods (`get_was_asleep` / `set_was_asleep` / `clear_drunk_state` / `clear_full_session`); `_save`/`_load` extend the flat JSON shape with the new field. `main.py` adds a transition detector at the top of `on_message` (drives wake reset + auto-close banner), refactors `_generate_voice_bleed` to return `(skill_name, sample_line, body_line)` instead of a single string, and adds one line to `cmd_close`.

**Tech Stack:** Python 3.10+, AstrBot v4 (`Star` class, no `@register_star`, `initialize`/`terminate` lifecycle), stdlib only (`json` already imported for parsing). Smoke tests stay inline as `if __name__ == "__main__":` blocks (existing repo convention; no pytest).

## Global Constraints

These come from the spec and apply to every task:

- **AstrBot v4 stays.** No `@register_star` decorator. Class name stays `VivianVale(Star)`. Lifecycle stays `async def initialize(self)` (no args) and `async def terminate(self)`. Metadata `name: vivian_vale` (Python identifier; no hyphens).
- **State persistence path:** `<plugin_dir>/state.json`. Plugin directory = `Path(__file__).parent`.
- **Thread-safety:** All `StateStore.set_*` / `record_*` / `clear_*` mutations run under `self._lock`; reads too.
- **Graceful degradation:** JSON load/save failures log a warning and fall back to in-memory defaults; the plugin never crashes on state I/O.
- **24-skill set is preserved.** Do not delete or rename any `skills/<id>/SKILL.md`.
- **Smoke-test convention:** Each module's `if __name__ == "__main__":` block contains `assert` checks; failures `raise SystemExit(1)`. Run with `python3 <module>.py`.
- **Commit cadence:** Every task ends with a commit. Use conventional-commit prefixes (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`).
- **Git push:** Tasks 1–3 stay local. Task 4 pushes the full branch to `WuShangyan/astrbot-DE-female` via the configured Clash proxy.
- **Spec scope (round 2):** Address exactly 4 spec gaps — wake reset (§4.4.2), auto-close banner (§4.4.7a), voice-bleed 3-tuple (§4.4.7b), cmd_close reset (§4.3). Do NOT add `enabled_skills` config, format post-processing, or `is_at_me` fast-path (deferred).

---

## File Structure

```
astrbot-DE-female/
├── main.py                   # MODIFIED (Task 2: on_message transitions, sleep-banner fix, cmd_close line; Task 3: voice-bleed refactor)
├── state.py                  # MODIFIED (Task 1: new field + 4 methods + JSON I/O extension + 3 tests)
├── banners.py                # UNCHANGED (all 5 banner functions already exist from round 1)
├── parsing.py                # UNCHANGED
├── epigraphs.py              # UNCHANGED (SKILL_EPIGRAPHS dict already has 24 entries)
├── personas/                 # UNCHANGED
├── skills/                   # UNCHANGED (24 SKILL.md files)
├── metadata.yaml             # UNCHANGED
├── plugin.json               # UNCHANGED
├── .gitignore                # UNCHANGED (state.json already gitignored from round 1)
├── docs/
│   ├── plan/
│   │   └── 2026-07-01-astrbot-vivian-vale-plugin.md  # UNCHANGED (original v3-era plan)
│   ├── specs/
│   │   ├── 2026-07-02-vivian-banner-and-state-port-design.md  # UNCHANGED (round 1 spec)
│   │   └── 2026-07-03-vivian-wake-reset-and-voice-bleed-3tuple-design.md  # UNCHANGED (this round's spec)
│   ├── CLAUDE.md             # UNCHANGED
│   └── plans/
│       └── 2026-07-03-vivian-wake-reset-and-voice-bleed-3tuple.md  # this plan
└── state.json                # gitignored; runtime state (extended JSON shape)
```

Decomposition rationale: `state.py` owns persistence and per-conv state; `main.py` owns AstrBot hooks and LLM interactions. Tasks 1 / 2 / 3 each touch one concern with one review gate.

---

## Task 1: Add `was_asleep_last_check` field + 4 methods to `state.py`

**Files:**
- Modify: `state.py` (add dataclass field, 4 methods, extend `_save`/`_load`, add 3 smoke tests)

**Interfaces:**
- Consumes: nothing (existing module is self-contained stdlib-only)
- Produces:
  - `was_asleep_last_check: dict[str, bool]` (new dataclass field, 13th)
  - `get_was_asleep(conv_id: str) -> bool`
  - `set_was_asleep(conv_id: str, was_asleep: bool) -> None`
  - `clear_drunk_state(conv_id: str) -> None` (resets drunk_count=0, last_drink_at=None, failure_streak=0)
  - `clear_full_session(conv_id: str) -> None` (resets last_skill + drunk_count + last_drink_at + last_direction_seen + failure_streak to None/0)
  - `_save()` and `_load()` extended to persist/restore `was_asleep_last_check`

- [ ] **Step 1: Add the 3 failing smoke tests to `state.py`'s `__main__` block**

Open `state.py`. Find the line `# -- summary ---------` (or similar marker just before the `if _failures:` print at the end of `__main__`). Insert the following test cases above the summary section:

```python
# -- Round 2: was_asleep + clear_drunk_state + clear_full_session -------

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
    """Wake reset (§4.4.2 + §4.3 cross-reference): drunk_count=0,
    last_drink_at=None, failure_streak=0. last_skill and direction
    are preserved per spec."""
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

- [ ] **Step 2: Run `state.py` to verify the 3 new tests fail**

Run:
```bash
python3 state.py
```

Expected: existing tests still pass, but the 3 new tests fail with `AttributeError: 'StateStore' object has no attribute 'get_was_asleep'` (or similar). Exit code 1.

- [ ] **Step 3: Add the dataclass field**

In the `StateStore` dataclass body, **after the `_last_skill` field** and before the closing of the class body, add:

```python
    was_asleep_last_check: dict[str, bool] = field(default_factory=dict)
```

(Final field count: 13.)

- [ ] **Step 4: Extend `_save()` to persist the new field**

Find the `_save` method (the dict literal that starts with `"de_enabled": self.de_enabled`). Add this line at the end of the dict literal (just before the closing `}`), keeping proper trailing comma:

```python
            "was_asleep_last_check": dict(self.was_asleep_last_check),
```

The complete `_save` method body should end with:

```python
    def _save(self) -> None:
        if self._path is None:
            return
        state = {
            "de_enabled": self.de_enabled,
            "de_toggle_ts": self.de_toggle_ts,
            "opened_today": self.opened_today,
            "drunk_counter": self.drunk_counter,
            "_drunk_timestamps": list(self._drunk_timestamps),
            "failure_streak": self.failure_streak,
            "_direction_cache": dict(self._direction_cache),
            "_voice_bleed_last_ts": self._voice_bleed_last_ts,
            "_voice_bleed_last_skill": self._voice_bleed_last_skill,
            "_silence_bleed_last_ts": self._silence_bleed_last_ts,
            "_last_message_ts": dict(self._last_message_ts),
            "_last_skill": dict(self._last_skill),
            "was_asleep_last_check": dict(self.was_asleep_last_check),
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            logging.warning(f"state.json save failed ({e}); state kept in memory only")
```

- [ ] **Step 5: Extend `_load()` to restore the new field**

Find the `_load` method (the chain of `self.X = data.get("X", default)` assignments). Add this line **after `self._last_skill = data.get("_last_skill", {})`**:

```python
        self.was_asleep_last_check = data.get("was_asleep_last_check", {})
```

- [ ] **Step 6: Add the 4 new methods**

Add the following methods to `StateStore`, **immediately after `set_last_skill`** (the last method added in round 1):

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

- [ ] **Step 7: Run `state.py` to verify all tests pass**

Run:
```bash
python3 state.py
```

Expected: existing tests + 3 new tests all PASS. Final line: `All smoke tests passed.`, exit code 0.

- [ ] **Step 8: Verify the in-memory case still works**

Add a temporary sanity check at the end of the `__main__` block (delete after verifying):

```python
# -- in-memory backward compatibility sanity check ------------------
s_inmem = StateStore()  # no path
s_inmem.set_was_asleep("conv-1", True)
assert s_inmem.get_was_asleep("conv-1") is True, "in-memory mode still works without path"
```

Run `python3 state.py` again; should still exit 0. **Remove the sanity check** before committing.

- [ ] **Step 9: Verify no regression in other smoke tests**

Run:
```bash
cd /Users/wushangyan/project/astrbot-DE-female
python3 banners.py
python3 parsing.py
```

Both should still exit 0. If either fails, you broke something outside Task 1's scope — debug before committing.

- [ ] **Step 10: Commit**

```bash
cd /Users/wushangyan/project/astrbot-DE-female
git add state.py
git commit -m "feat(state): was_asleep flag + clear_drunk_state + clear_full_session"
```

---

## Task 2: `main.py` transition detector + sleep-window banner fix + cmd_close

**Files:**
- Modify: `main.py` (3 surgical edits)

This task has no automated test (the relevant logic requires AstrBot event injection). Verification = running existing smoke tests for regression.

- [ ] **Step 1: Replace the top of `on_message` with the transition detector**

Find the existing `on_message` function (it's the one decorated with `@filter.event_message_type(EventMessageType.ALL, priority=1)`). The function starts with:

```python
    async def on_message(self, event: AstrMessageEvent):
        now = datetime.datetime.now()
        self.state.maybe_reset_daily(now.hour)

        # ── 物理层: 睡眠窗口自动关闭 DE ──
        if self.state.check_sleep_window(now.hour) and self.state.de_enabled:
            conv_id = event.unified_msg_origin
            self.state.set_open(conv_id, False)
            self.state.opened_today = False  # separate from set_open — sleep truly closes the day
            yield event.plain_result(render_sleep_banner())
            return
```

Replace this entire block with:

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

Leave the rest of `on_message` (group `@`-filter, direction inference, voice-bleed gate) untouched — Task 3 handles the voice-bleed refactor separately.

- [ ] **Step 2: Add `failure_streak = 0` to `cmd_close` (§4.3 strict)**

Find `cmd_close`:

```python
    @filter.command("关门")
    async def cmd_close(self, event: AstrMessageEvent):
        conv_id = event.unified_msg_origin
        last_skill = self.state.get_last_skill(conv_id)
        self.state.set_open(conv_id, False)
        yield event.plain_result(render_close_banner(last_skill))
```

Replace with:

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

- [ ] **Step 3: Run all smoke tests to confirm no regression**

```bash
cd /Users/wushangyan/project/astrbot-DE-female
python3 banners.py
python3 state.py
python3 parsing.py
```

All three should still exit 0. If anything fails, you introduced a syntax error or import issue — fix before committing.

- [ ] **Step 4: Verify `main.py` still parses (no syntax errors)**

Run:
```bash
cd /Users/wushangyan/project/astrbot-DE-female
python3 -c "import ast; ast.parse(open('main.py').read()); print('main.py parses OK')"
```

Expected: `main.py parses OK`. If this fails, you have a syntax error to fix before continuing.

- [ ] **Step 5: Commit**

```bash
cd /Users/wushangyan/project/astrbot-DE-female
git add main.py
git commit -m "refactor(main): wake/sleep transition detector + auto-close banner + cmd_close reset"
```

---

## Task 3: `main.py` voice-bleed 3-tuple refactor

**Files:**
- Modify: `main.py` (refactor `_generate_voice_bleed` + update caller in `on_message` + add `import json` if missing)

This task has no automated test (LLM call behavior cannot be unit-tested without an LLM). Verification = code review + manual docker test in Task 4.

- [ ] **Step 1: Ensure `import json` is at the top of `main.py`**

Open `main.py`. Check the top of the file (around lines 1–10). If `import json` is not already present, add it. (If it is, skip this step.)

If adding, the import block should look like:

```python
import asyncio
import datetime
import json
import random
from pathlib import Path
```

(The existing imports are `asyncio`, `datetime`, `random`, `pathlib.Path`.)

- [ ] **Step 2: Find the existing `_generate_voice_bleed` method**

In `main.py`, find the `_generate_voice_bleed` method. Its signature is currently:

```python
    async def _generate_voice_bleed(self, event: AstrMessageEvent) -> str | None:
        """调 LLM 生成一段与上下文相关的技能独白,不显示技能名"""
        # ... (long prompt + LLM call + completion_text strip + scrub_identity + record_voice_bleed + return)
```

The full body returns a string or None.

- [ ] **Step 3: Replace the entire method with the 3-tuple version**

Replace the method (signature + body) with:

```python
    async def _generate_voice_bleed(
        self, event: AstrMessageEvent
    ) -> tuple[str, str, str] | None:
        """Voice-bleed: code picks skill_name and body_line; LLM only writes
        the sample_line (one short utterance matching the chosen skill's voice).

        Returns (skill_name, sample_line, body_line) or None on any failure.
        Caller passes the tuple to render_voice_bleed_banner(...).
        """
        # 1. Code-side: pick a skill (random, excluding last voice-bleed skill)
        from .epigraphs import SKILL_EPIGRAPHS  # relative import (matches AstrBot v4 plugin convention)

        exclude = self.state._voice_bleed_last_skill
        candidates = [k for k in SKILL_EPIGRAPHS if k != exclude]
        if not candidates:
            candidates = list(SKILL_EPIGRAPHS.keys())
        skill_name = random.choice(candidates)

        # 2. Code-side: pick a Vivian reaction line
        from .banners import _VOICE_BLEED_BODY_LINES  # relative import
        body_line = random.choice(_VOICE_BLEED_BODY_LINES)

        # 3. LLM-side: write the skill's whisper (one sentence)
        skill_desc = SKILL_EPIGRAPHS.get(skill_name, "")
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

Notes on the local imports:
- `from epigraphs import SKILL_EPIGRAPHS` — done inside the method to avoid circular import risk and keep top-of-file imports clean.
- `from banners import _VOICE_BLEED_BODY_LINES` — same rationale; `_VOICE_BLEED_BODY_LINES` is defined in `banners.py` from round 1.

- [ ] **Step 4: Update the voice-bleed caller in `on_message`**

Find this block in `on_message` (it appears after the direction-inference block, before `inject_persona`):

```python
        # ── DE OFF: voice bleed(LLM 生成,与上下文相关) ──
        if not self.state.de_enabled and self._should_voice_bleed():
            text = await self._generate_voice_bleed(event)
            if text:
                yield event.plain_result(text)
```

Replace with:

```python
        # ── DE OFF: voice bleed(3-tuple: 技能名 + 独白 + 本体一行) ──
        if not self.state.de_enabled and self._should_voice_bleed():
            triple = await self._generate_voice_bleed(event)
            if triple:
                skill_name, sample_line, body_line = triple
                yield event.plain_result(
                    render_voice_bleed_banner(skill_name, sample_line, body_line)
                )
```

- [ ] **Step 5: Run smoke tests to confirm no regression**

```bash
cd /Users/wushangyan/project/astrbot-DE-female
python3 banners.py
python3 state.py
python3 parsing.py
```

All three should still exit 0. The refactor doesn't touch any module that has smoke tests, but run them anyway to catch accidental cross-file breakage.

- [ ] **Step 6: Verify `main.py` still parses**

```bash
cd /Users/wushangyan/project/astrbot-DE-female
python3 -c "import ast; ast.parse(open('main.py').read()); print('main.py parses OK')"
```

Expected: `main.py parses OK`.

- [ ] **Step 7: Verify `render_voice_bleed_banner` is imported**

In `main.py`, find the `from .banners import (...)` block. Confirm `render_voice_bleed_banner` is in the import list. (It was added in round 1's Task 4 wiring and is still there — verify, don't re-add.)

The import block should include:

```python
from .banners import (
    render_open_banner,
    render_close_banner,
    render_clear_banner,
    render_haze_banner,
    render_voice_bleed_banner,  # ← this one
    render_sleep_banner,
)
```

If `render_voice_bleed_banner` is missing, add it.

- [ ] **Step 8: Commit**

```bash
cd /Users/wushangyan/project/astrbot-DE-female
git add main.py
git commit -m "refactor(main): voice-bleed returns 3-tuple (skill, sample, body) for framed banner"
```

---

## Task 4: Push + docker end-to-end verification (user-side)

**Files:** none (manual operations only)

This task verifies the integration in the running AstrBot container. Not committable as code; it's the final acceptance gate.

- [ ] **Step 1: Push the branch via the configured Clash proxy**

```bash
cd /Users/wushangyan/project/astrbot-DE-female
git log --oneline -7   # confirm 3 new commits on top of d6a840e (the spec doc commit)
git push origin main
```

Expected: 3 new commits land on `WuShangyan/astrbot-DE-female/main`. (Proxy is already configured in `~/.gitconfig` from a previous round.)

- [ ] **Step 2: Reload the plugin in the docker container**

```bash
sudo docker exec astrbot touch /AstrBot/data/plugins/vivian_vale/main.py
# Or use AstrBot's reload API:
# curl -X POST http://localhost:6185/api/plugin/reload -H "Content-Type: application/json" -d '{"name": "vivian_vale"}'
```

Expected: no errors in docker logs (`sudo docker logs astrbot --tail 50`). The plugin's `initialize()` runs and reads the extended JSON shape.

- [ ] **Step 3: Verify ASCII open banner (regression check, round 1 feature)**

In a private chat with the bot, send `芝麻开门`. Expected: ASCII frame banner as in round 1.

- [ ] **Step 4: Verify wake transition triggers `clear_drunk_state`**

This test requires patience — you'll need to set up drunk state, then trigger a wake transition manually. In docker:

```bash
# Step 4a: Manually create drunk state in JSON (simulate "drunk last night")
sudo docker exec astrbot bash -c '
  cd /AstrBot/data/plugins/vivian_vale
  python3 -c "
import json
from pathlib import Path
p = Path(\"state.json\")
if p.exists():
    d = json.loads(p.read_text())
    for conv in d.get(\"conversations\", {}).values():
        conv[\"drunk_count\"] = 5
        conv[\"failure_streak\"] = 3
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False))
    print(\"set drunk_count=5, failure_streak=3 on all convs\")
else:
    print(\"no state.json yet\")
"
'

# Step 4b: Send a message to the bot
# (the bot will respond, and on_message will run)
```

Wait — this test only validates `clear_drunk_state` if a wake transition happens, which requires AstrBot to have been "asleep" before. For a quick verification, just check that `drunk_count` is reset by inspecting state.json after sending any message (it shouldn't be — drunk_count only resets on wake, not on every message). For the actual transition, you'd need to manipulate `was_asleep_last_check` to `True` and then send a message during the wake cycle (8:00-23:59). Since we can't time-travel, the docker test for wake reset is best verified by:

1. Manually set `was_asleep_last_check` to `{"conv-1": true}` in state.json
2. Send a message at any time outside the sleep window (any time 8:00-3:59)
3. Verify `was_asleep_last_check[conv-1]` is now `false` and `failure_streak` is reset to 0 for that conv

```bash
# After sending the message, check:
sudo docker exec astrbot cat /AstrBot/data/plugins/vivian_vale/state.json | grep -A2 "was_asleep"
# Expected: "was_asleep_last_check": {"aiocqhttp:PrivateMessage:...": false}
```

- [ ] **Step 5: Verify auto-close banner (the key new behavior)**

This is the most important test — verify that when DE is ON and the user sends a message during the sleep window, the close banner appears (with last-skill epigraph) instead of the sleep flavor.

```bash
# Step 5a: Set up state — DE enabled with a last_skill set
sudo docker exec astrbot bash -c '
  cd /AstrBot/data/plugins/vivian_vale
  python3 -c "
import json
from pathlib import Path
p = Path(\"state.json\")
if p.exists():
    d = json.loads(p.read_text())
    for cid, conv in d.get(\"conversations\", {}).items():
        conv[\"_last_skill\"] = {cid: \"逻辑思维\"}
        conv[\"open\"] = True
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False))
"
'

# Step 5b: Manually set the time-of-day to inside the sleep window
# (You can'\''t actually change system time in production, but you can edit was_asleep_last_check to force the trigger:)
sudo docker exec astrbot bash -c '
  cd /AstrBot/data/plugins/vivian_vale
  python3 -c "
import json
from pathlib import Path
p = Path(\"state.json\")
d = json.loads(p.read_text())
for cid in d.get(\"conversations\", {}):
    d[\"conversations\"][cid][\"was_asleep_last_check\"] = False  # simulate last msg during wake
    d[\"conversations\"][cid][\"open\"] = True
p.write_text(json.dumps(d, indent=2, ensure_ascii=False))
"
'

# Step 5c: Wait for 04:00-08:00 local time (or use docker exec with simulated time)
# Easier: change docker container time via docker run flags (but that'\''s invasive).
# Alternative: temporarily edit check_sleep_window to return True, send a message, observe.
```

Since simulating "now is 04:00" is hard, the pragmatic test is:

1. Edit `state.py` temporarily to make `check_sleep_window` always return `True` (for testing)
2. Restart the plugin
3. Send `芝麻开门` → set DE enabled, then send any message
4. Expected: close banner (with last-skill epigraph) appears, NOT sleep_banner
5. Restore `state.py`

**Or simpler**: send a message at 4:30 AM local time on your real machine. This actually verifies the spec.

- [ ] **Step 6: Verify voice-bleed emits the 4-line framed banner**

In DE OFF mode, send a message and observe the voice-bleed banner (1/8 probability). Expected: framed banner with `░▒▓` + `〔技能名〕独白` + 本体一行 + `░▒▓`, **4 lines**, NOT a single line.

If voice-bleed doesn't fire on the first message (1/8 probability), send several messages until it fires. The banner should have the correct frame structure.

- [ ] **Step 7: Verify all `state.json` fields round-trip**

After all the above tests, inspect `state.json`:

```bash
sudo docker exec astrbot cat /AstrBot/data/plugins/vivian_vale/state.json
```

Expected: JSON includes the new field `was_asleep_last_check` with per-conv booleans.

- [ ] **Step 8: Done**

The round 2 port is live. Report back with a summary of what worked and any edge cases encountered.