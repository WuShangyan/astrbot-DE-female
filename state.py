"""Conversation-level state management for the AstrBot Vivian Vale plugin.

Tracks: DE mode toggle, drunk counter with sliding window, sleep window,
per-conversation direction cache, failure streak for hybrid rhythm, and
voice-bleed gating.  Self-contained -- no external dependencies.
"""

from __future__ import annotations

import json
import logging
import random
import tempfile
import threading
import time
from pathlib import Path
from typing import Literal, Optional

# Sliding window size for drunk-counter pruning (12 hours in seconds).
_DRUNK_WINDOW: int = 12 * 3600

# Voice-bleed cool-down (4 hours in seconds).
_VOICE_BLEED_COOLDOWN: int = 4 * 3600


class StateStore:
    """Mutable, single-session state bag with optional JSON persistence.

    Pass ``path`` to enable JSON persistence; omit for pure in-memory use.
    Field mutations are serialised with an internal ``threading.Lock`` and
    (when persistence is enabled) flushed to disk after each mutating call.
    Not safe to share a single instance across processes -- one file per
    process. Field defaults are applied in ``__init__`` so custom kwargs
    (e.g. ``opened_today=True``) override them on construction -- this
    keeps the test-only constructors working.
    """

    # -- DE mode toggle ---------------------------------------------------
    de_enabled: bool
    de_toggle_ts: float

    # -- daily open tracking (voice-bleed gate) ---------------------------
    opened_today: bool

    # -- drunk state ------------------------------------------------------
    drunk_counter: int
    _drunk_timestamps: list[float]

    # -- failure streak (hybrid rhythm, spec 4.3) -------------------------
    failure_streak: int

    # -- per-conversation direction cache ---------------------------------
    _direction_cache: dict[str, Optional[Literal["清", "混"]]]

    # -- voice-bleed tracking ---------------------------------------------
    _voice_bleed_last_ts: float
    _voice_bleed_last_skill: str

    # -- silence-bleed (proactive muttering after long silence) -----------
    _silence_bleed_last_ts: float
    _last_message_ts: dict[str, float]

    # -- per-conversation last skill (banner source) ----------------------
    _last_skill: dict[str, str | None]

    # -- per-conversation sleep-edge flag (Task 3) ------------------------
    was_asleep_last_check: dict[str, bool]

    # -- persistence infrastructure ---------------------------------------
    _path: Path | None
    _lock: threading.Lock

    def __init__(self, path: Path | None = None, **kwargs) -> None:
        """State store. Pass ``path`` to enable JSON persistence; omit for
        in-memory mode. Keyword args override field defaults -- kept for
        back-compat with the legacy dataclass-style test constructors."""
        self.de_enabled = kwargs.pop("de_enabled", False)
        self.de_toggle_ts = kwargs.pop("de_toggle_ts", 0.0)
        self.opened_today = kwargs.pop("opened_today", False)
        self.drunk_counter = kwargs.pop("drunk_counter", 0)
        self._drunk_timestamps = kwargs.pop("_drunk_timestamps", [])
        self.failure_streak = kwargs.pop("failure_streak", 0)
        self._direction_cache = kwargs.pop("_direction_cache", {})
        self._voice_bleed_last_ts = kwargs.pop("_voice_bleed_last_ts", 0.0)
        self._voice_bleed_last_skill = kwargs.pop("_voice_bleed_last_skill", "")
        self._silence_bleed_last_ts = kwargs.pop("_silence_bleed_last_ts", 0.0)
        self._last_message_ts = kwargs.pop("_last_message_ts", {})
        self._last_skill = {}
        self.was_asleep_last_check = {}
        if kwargs:
            raise TypeError(
                f"StateStore.__init__ got unexpected keyword args: "
                f"{sorted(kwargs.keys())}"
            )
        self._path = path
        self._lock = threading.Lock()
        self._load()

    def _save(self) -> None:
        """Persist ALL state to JSON. Flat shape -- typed fields at top
        level, per-conversation dicts nested by conv_id. No-op when no
        path was supplied (pure in-memory mode)."""
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
            logging.warning(
                f"state.json save failed ({e}); state kept in memory only"
            )

    def _load(self) -> None:
        """Restore state from JSON. Silent fallback to default state on any
        error -- corrupt, missing, or unreadable file -> fresh defaults."""
        if self._path is None or not self._path.exists():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            if not raw.strip():
                return
            data = json.loads(raw)
            self.de_enabled = data.get("de_enabled", False)
            self.de_toggle_ts = data.get("de_toggle_ts", 0.0)
            self.opened_today = data.get("opened_today", False)
            self.drunk_counter = data.get("drunk_counter", 0)
            self._drunk_timestamps = data.get("_drunk_timestamps", [])
            self.failure_streak = data.get("failure_streak", 0)
            self._direction_cache = data.get("_direction_cache", {})
            self._voice_bleed_last_ts = data.get("_voice_bleed_last_ts", 0.0)
            self._voice_bleed_last_skill = data.get(
                "_voice_bleed_last_skill", ""
            )
            self._silence_bleed_last_ts = data.get(
                "_silence_bleed_last_ts", 0.0
            )
            self._last_message_ts = data.get("_last_message_ts", {})
            self._last_skill = data.get("_last_skill", {})
            self.was_asleep_last_check = data.get("was_asleep_last_check", {})
        except (json.JSONDecodeError, OSError) as e:
            logging.warning(
                f"state.json corrupt/unreadable ({e}); using empty default"
            )

    # ---------------------------------------------------------------------
    # Drunk helpers
    # ---------------------------------------------------------------------

    def touch_drunk(self, direction: str) -> None:
        """Record a drink event and prune stale timestamps.

        * Increment ``drunk_counter`` only when *direction* is ``"混"``.
        * Prune entries older than the 12-hour sliding window so the
          counter naturally decays.
        """
        with self._lock:
            now = time.time()

            # Prune old entries outside the sliding window.
            cutoff = now - _DRUNK_WINDOW
            self._drunk_timestamps = [
                ts for ts in self._drunk_timestamps if ts > cutoff
            ]
            # Also fix the counter to match pruned timestamps.
            self.drunk_counter = len(self._drunk_timestamps)

            if direction == "混":
                self._drunk_timestamps.append(now)
                self.drunk_counter += 1

            self._save()

    def is_drunk(self) -> bool:
        """Return True when the drunk counter has reached the threshold."""
        return self.drunk_counter >= 3

    # ---------------------------------------------------------------------
    # Sleep window
    # ---------------------------------------------------------------------

    @staticmethod
    def check_sleep_window(hour: int) -> bool:
        """Return True when *hour* falls inside the 04:00-07:59 sleep window."""
        return 4 <= hour < 8

    # ---------------------------------------------------------------------
    # Daily reset
    # ---------------------------------------------------------------------

    def maybe_reset_daily(self, now_hour: int) -> None:
        """Reset ``opened_today`` at 08:00 to start a fresh voice-bleed day."""
        with self._lock:
            if now_hour == 8:
                self.opened_today = False
            self._save()

    # ---------------------------------------------------------------------
    # Failure streak (hybrid rhythm, spec section 4.3)
    # ---------------------------------------------------------------------

    def record_failure(self, is_failure: bool) -> None:
        """Track consecutive non-failure replies.

        * ``is_failure=True``  -> reset the streak to 0.
        * ``is_failure=False`` -> increment by 1.
        """
        with self._lock:
            if is_failure:
                self.failure_streak = 0
            else:
                self.failure_streak += 1
            self._save()

    def should_force_failure(self) -> bool:
        """Force a [失败] when 8+ consecutive non-failures have been emitted."""
        return self.failure_streak >= 8

    def should_hint_failure(self) -> bool:
        """Nudge toward failure when 5+ consecutive non-failures have been emitted."""
        return self.failure_streak >= 5

    # ---------------------------------------------------------------------
    # Per-conversation direction cache
    # ---------------------------------------------------------------------

    def get_direction(self, conv_id: str) -> Optional[Literal["清", "混"]]:
        """Return the cached direction for *conv_id*, or ``None``."""
        return self._direction_cache.get(conv_id)

    def set_direction(
        self, conv_id: str, direction: Optional[Literal["清", "混"]]
    ) -> None:
        """Cache (or clear) the direction for *conv_id*. Persists to JSON."""
        with self._lock:
            self._direction_cache[conv_id] = direction
            self._save()

    # ---------------------------------------------------------------------
    # Voice-bleed gating (spec section 4.4.7b)
    # ---------------------------------------------------------------------

    def can_voice_bleed(self) -> bool:
        """Decide whether a spontaneous voice-bleed may fire.

        All four gates must pass:
        1. DE mode is NOT active.
        2. The DE door has NOT been opened today.
        3. At least 4 hours since the last bleed.
        4. A 1-in-8 random roll succeeds.
        """
        if self.de_enabled:
            return False
        if self.opened_today:
            return False
        now = time.time()
        if (now - self._voice_bleed_last_ts) < _VOICE_BLEED_COOLDOWN:
            return False
        return random.random() < (1 / 8)

    def record_voice_bleed(self, skill: str) -> None:
        """Update the last voice-bleed timestamp and skill name."""
        with self._lock:
            self._voice_bleed_last_ts = time.time()
            self._voice_bleed_last_skill = skill
            self._save()

    # ---------------------------------------------------------------------
    # Silence-bleed helpers (proactive muttering after long silence)
    # ---------------------------------------------------------------------

    # Silence-bleed cool-down: 5 days in seconds.
    _SILENCE_BLEED_COOLDOWN: int = 5 * 24 * 3600

    # Silence threshold: 12 hours in seconds.
    _SILENCE_THRESHOLD: int = 12 * 3600

    def touch_last_message(self, conv_id: str) -> None:
        """Record that a message was sent in this conversation."""
        with self._lock:
            self._last_message_ts[conv_id] = time.time()
            self._save()

    def can_silence_bleed(self, conv_id: str) -> bool:
        """Check if a silence-bleed can fire for this conversation.

        Gates:
        1. DE mode is OFF.
        2. 12+ hours since last message in this conversation.
        3. 5+ days since last silence-bleed (global).
        """
        if self.de_enabled:
            return False

        last_msg = self._last_message_ts.get(conv_id, 0.0)
        if last_msg == 0.0:
            return False  # no message history, skip

        now = time.time()
        if now - last_msg < self._SILENCE_THRESHOLD:
            return False  # not enough silence

        if now - self._silence_bleed_last_ts < self._SILENCE_BLEED_COOLDOWN:
            return False  # too soon since last bleed

        return True

    def record_silence_bleed(self) -> None:
        """Mark that a silence-bleed just fired."""
        with self._lock:
            self._silence_bleed_last_ts = time.time()
            self._save()

    # ---------------------------------------------------------------------
    # Toggle / per-conversation skill tracking (Task 2)
    # ---------------------------------------------------------------------

    def set_open(self, conv_id: str, open_: bool, toggle_ts: float = 0.0) -> None:
        """User-triggered toggle of DE mode. Persists to JSON.

        ``conv_id`` is currently unused (``de_enabled`` is global) but kept
        in the API for future per-conv scoping. On open, also resets the
        per-conv ``last_skill`` so the next close-banner falls back to the
        opening epigraph.
        """
        with self._lock:
            self.de_enabled = open_
            if open_:
                self.opened_today = True
                self.de_toggle_ts = toggle_ts
                self._last_skill[conv_id] = None
            self._save()

    def get_last_skill(self, conv_id: str) -> str | None:
        """The most recently triggered skill name for this conversation,
        or ``None`` if no skill has fired yet (or right after a fresh
        open)."""
        with self._lock:
            return self._last_skill.get(conv_id)

    def set_last_skill(self, conv_id: str, name: str | None) -> None:
        """Record the skill that just fired, so the close banner can quote
        its epigraph. Persists to JSON."""
        with self._lock:
            self._last_skill[conv_id] = name
            self._save()

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
        """Wake hard-reset (§4.4.2 + §4.3 cross-reference): clears the three
        global drunk-related typed fields (drunk_counter, _drunk_timestamps,
        failure_streak). Per spec these should be per-conv but the existing
        implementation has them as global dataclass fields; round 2 follows
        the existing shape to avoid a state-model refactor outside scope."""
        with self._lock:
            self.drunk_counter = 0
            self._drunk_timestamps = []
            self.failure_streak = 0
            self._save()


    def clear_full_session(self, conv_id: str) -> None:
        """§4.4.7a auto-close cleanup: clears per-conv _last_skill +
        _direction_cache for this conv, plus the three global drunk-related
        fields. So the next DE session starts fresh for this conversation."""
        with self._lock:
            self._last_skill[conv_id] = None
            self._direction_cache[conv_id] = None
            self.drunk_counter = 0
            self._drunk_timestamps = []
            self.failure_streak = 0
            self._save()


# ======================================================================
# Smoke tests
# ======================================================================

if __name__ == "__main__":
    import math

    _failures: list[str] = []

    def _assert(condition: bool, label: str) -> None:
        if not condition:
            _failures.append(label)
            print(f"  FAIL  {label}")
        else:
            print(f"  PASS  {label}")

    # -- touch_drunk / is_drunk ------------------------------------------
    s = StateStore()
    s.touch_drunk("清")  # direction is clean -- counter should NOT increase
    _assert(s.drunk_counter == 0, "touch_drunk(clean) does not increment")
    _assert(not s.is_drunk(), "not drunk at 0")

    s.touch_drunk("混")
    _assert(s.drunk_counter == 1, "drunk_counter == 1 after first murky")
    s.touch_drunk("混")
    _assert(s.drunk_counter == 2, "drunk_counter == 2")
    _assert(not s.is_drunk(), "not drunk at 2")
    s.touch_drunk("混")
    _assert(s.drunk_counter == 3, "drunk_counter == 3")
    _assert(s.is_drunk(), "drunk at 3")

    # -- sliding window pruning ------------------------------------------
    s2 = StateStore()
    # Insert 3 timestamps manually -- all 13 hours ago (outside window).
    old = time.time() - 13 * 3600
    s2._drunk_timestamps = [old, old + 10, old + 20]
    s2.drunk_counter = 3
    s2.touch_drunk("混")  # should prune all 3, then add 1
    _assert(s2.drunk_counter == 1, "pruned stale timestamps, counter == 1")
    _assert(not s2.is_drunk(), "not drunk after pruning")

    # -- check_sleep_window ----------------------------------------------
    _assert(StateStore.check_sleep_window(4) is True, "4 is in sleep window")
    _assert(StateStore.check_sleep_window(7) is True, "7 is in sleep window")
    _assert(StateStore.check_sleep_window(3) is False, "3 is NOT in sleep window")
    _assert(StateStore.check_sleep_window(8) is False, "8 is NOT in sleep window")

    # -- maybe_reset_daily -----------------------------------------------
    s3 = StateStore(opened_today=True)
    s3.maybe_reset_daily(7)
    _assert(s3.opened_today is True, "no reset at hour 7")
    s3.maybe_reset_daily(8)
    _assert(s3.opened_today is False, "reset at hour 8")

    # -- failure streak --------------------------------------------------
    s4 = StateStore()
    _assert(s4.failure_streak == 0, "initial failure_streak == 0")
    s4.record_failure(False)  # non-failure -> increment
    s4.record_failure(False)
    s4.record_failure(False)
    _assert(s4.failure_streak == 3, "failure_streak == 3 after 3 non-failures")
    _assert(not s4.should_hint_failure(), "no hint at 3")
    _assert(not s4.should_force_failure(), "no force at 3")

    for _ in range(5):  # total 8
        s4.record_failure(False)
    _assert(s4.failure_streak == 8, "failure_streak == 8")
    _assert(s4.should_hint_failure(), "hint at 8")
    _assert(s4.should_force_failure(), "force at 8")

    s4.record_failure(True)  # actual failure -> reset
    _assert(s4.failure_streak == 0, "failure_streak reset to 0 on failure")

    # -- direction cache -------------------------------------------------
    s5 = StateStore()
    _assert(s5.get_direction("conv-1") is None, "default direction is None")
    s5.set_direction("conv-1", "清")
    _assert(s5.get_direction("conv-1") == "清", "direction is now 清")
    s5.set_direction("conv-1", "混")
    _assert(s5.get_direction("conv-1") == "混", "direction is now 混")

    # -- can_voice_bleed gates -------------------------------------------
    s6 = StateStore(de_enabled=True)
    _assert(not s6.can_voice_bleed(), "blocked when de_enabled")

    s6b = StateStore(opened_today=True)
    _assert(not s6b.can_voice_bleed(), "blocked when opened_today")

    s6c = StateStore()
    s6c._voice_bleed_last_ts = time.time()  # just bled
    _assert(not s6c.can_voice_bleed(), "blocked within cooldown")

    # -- record_voice_bleed ----------------------------------------------
    s7 = StateStore()
    before = time.time()
    s7.record_voice_bleed("食髓知味")
    _assert(
        s7._voice_bleed_last_ts >= before,
        "voice bleed ts updated",
    )
    _assert(
        s7._voice_bleed_last_skill == "食髓知味",
        "voice bleed skill recorded",
    )

    # -- JSON persistence (Task 2) ---------------------------------------

    def test_set_open_persists_across_instances():
        """set_open(conv_id, True) → JSON survives reload."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            s1 = StateStore(path)
            s1.set_open("conv-1", True, toggle_ts=12345.0)
            s2 = StateStore(path)
            assert s2.de_enabled is True, "de_enabled persisted via set_open → reload"
            assert s2.de_toggle_ts == 12345.0, "de_toggle_ts persisted"
            assert s2.opened_today is True, "opened_today persisted"
            assert s2.get_last_skill("conv-1") is None, "last_skill reset to None on open"

    def test_full_state_persists_across_reload():
        """All typed dataclass fields survive a reload via JSON."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            s1 = StateStore(path)
            s1.set_open("conv-A", True)
            s1.record_failure(True)  # sets failure_streak = 0
            s1.record_failure(False)
            s1.record_failure(False)  # streak = 2
            s1.touch_drunk("混")  # drunk_counter = 1
            s1.touch_drunk("混")  # drunk_counter = 2
            s1.set_direction("conv-A", "清")
            s1.set_last_skill("conv-A", "逻辑思维")
            s1.touch_last_message("conv-A")
            s2 = StateStore(path)
            assert s2.failure_streak == 2, "failure_streak persisted"
            assert s2.drunk_counter == 2, "drunk_counter persisted"
            assert s2.get_direction("conv-A") == "清", "direction cache persisted"
            assert s2.get_last_skill("conv-A") == "逻辑思维", "last_skill persisted"
            assert "conv-A" in s2._last_message_ts, "last_message_ts persisted"

    def test_corrupt_json_falls_back_to_empty():
        """Bad JSON on disk → empty default state, no exception."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            path.write_text("not json", encoding="utf-8")
            s = StateStore(path)
            # Should not raise; state starts at dataclass defaults
            assert s.de_enabled is False, "de_enabled defaults to False on corrupt JSON"
            assert s.failure_streak == 0, "failure_streak defaults to 0 on corrupt JSON"
            assert s.get_last_skill("any") is None, "last_skill defaults to None on corrupt JSON"

    def test_missing_json_file_creates_on_first_save():
        """No file on disk → first mutating call creates it."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "new_state.json"
            assert not path.exists(), "precondition: file does not exist"
            s = StateStore(path)
            s.set_open("conv-1", True)
            assert path.exists(), "state.json created on first set_open"
            data = json.loads(path.read_text("utf-8"))
            # Flat JSON shape — fields at top level, per-conv dicts nested
            assert data["de_enabled"] is True, "de_enabled at JSON top level"
            assert data["_last_skill"]["conv-1"] is None, "_last_skill nested dict"

    test_set_open_persists_across_instances()
    test_full_state_persists_across_reload()
    test_corrupt_json_falls_back_to_empty()
    test_missing_json_file_creates_on_first_save()

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

    # -- summary ---------------------------------------------------------
    print()
    if _failures:
        print(f"FAILED: {len(_failures)} test(s): {', '.join(_failures)}")
        raise SystemExit(1)
    else:
        print("All smoke tests passed.")
