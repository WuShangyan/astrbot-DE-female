"""Conversation-level state management for the AstrBot Vivian Vale plugin.

Tracks: DE mode toggle, drunk counter with sliding window, sleep window,
per-conversation direction cache, failure streak for hybrid rhythm, and
voice-bleed gating.  Self-contained -- no external dependencies.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

# Sliding window size for drunk-counter pruning (12 hours in seconds).
_DRUNK_WINDOW: int = 12 * 3600

# Voice-bleed cool-down (4 hours in seconds).
_VOICE_BLEED_COOLDOWN: int = 4 * 3600


@dataclass
class StateStore:
    """Mutable, single-session state bag.

    Not persisted to disk and not thread-safe on its own -- the caller
    (typically the AstrBot event handler) is responsible for serialising
    access if needed.
    """

    # -- DE mode toggle ---------------------------------------------------
    de_enabled: bool = False
    de_toggle_ts: float = 0.0

    # -- daily open tracking (voice-bleed gate) ---------------------------
    opened_today: bool = False

    # -- drunk state ------------------------------------------------------
    drunk_counter: int = 0
    _drunk_timestamps: list[float] = field(default_factory=list)

    # -- failure streak (hybrid rhythm, spec 4.3) -------------------------
    failure_streak: int = 0

    # -- per-conversation direction cache ---------------------------------
    _direction_cache: dict[str, Optional[Literal["清", "混"]]] = field(
        default_factory=dict,
    )

    # -- voice-bleed tracking ---------------------------------------------
    _voice_bleed_last_ts: float = 0.0
    _voice_bleed_last_skill: str = ""

    # -- silence-bleed (proactive muttering after long silence) -----------
    _silence_bleed_last_ts: float = 0.0
    _last_message_ts: dict[str, float] = field(default_factory=dict)

    # ---------------------------------------------------------------------
    # Drunk helpers
    # ---------------------------------------------------------------------

    def touch_drunk(self, direction: str) -> None:
        """Record a drink event and prune stale timestamps.

        * Increment ``drunk_counter`` only when *direction* is ``"混"``.
        * Prune entries older than the 12-hour sliding window so the
          counter naturally decays.
        """
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
        if now_hour == 8:
            self.opened_today = False

    # ---------------------------------------------------------------------
    # Failure streak (hybrid rhythm, spec section 4.3)
    # ---------------------------------------------------------------------

    def record_failure(self, is_failure: bool) -> None:
        """Track consecutive non-failure replies.

        * ``is_failure=True``  -> reset the streak to 0.
        * ``is_failure=False`` -> increment by 1.
        """
        if is_failure:
            self.failure_streak = 0
        else:
            self.failure_streak += 1

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
        """Cache (or clear) the direction for *conv_id*."""
        self._direction_cache[conv_id] = direction

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
        self._voice_bleed_last_ts = time.time()
        self._voice_bleed_last_skill = skill

    # ---------------------------------------------------------------------
    # Silence-bleed helpers (proactive muttering after long silence)
    # ---------------------------------------------------------------------

    # Silence-bleed cool-down: 5 days in seconds.
    _SILENCE_BLEED_COOLDOWN: int = 5 * 24 * 3600

    # Silence threshold: 12 hours in seconds.
    _SILENCE_THRESHOLD: int = 12 * 3600

    def touch_last_message(self, conv_id: str) -> None:
        """Record that a message was sent in this conversation."""
        self._last_message_ts[conv_id] = time.time()

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
        self._silence_bleed_last_ts = time.time()


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

    # -- summary ---------------------------------------------------------
    print()
    if _failures:
        print(f"FAILED: {len(_failures)} test(s): {', '.join(_failures)}")
        raise SystemExit(1)
    else:
        print("All smoke tests passed.")
