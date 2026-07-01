"""Pure parsing helpers for toggle commands and skill-name extraction.

These functions depend only on their inputs — no AstrBot imports — so
they can be unit-tested in isolation.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

ToggleAction = Literal["open", "close"]

_OPEN_KEYWORD = "芝麻开门"
_CLOSE_KEYWORD = "芝麻关门"

# Matches the FIRST bracketed name on the first non-blank line followed by
# "[成功]" or "[失败]". Group 1 = skill name; Group 2 = 成功|失败.
_SKILL_LINE_RE = re.compile(r"^\[([^\]]+)\]\s*\[(成功|失败)\]")


def detect_toggle(message_text: str, at_me: bool) -> Optional[ToggleAction]:
    """Detect if a message is a toggle command.

    Requires both `at_me=True` (bot was @-mentioned) AND one of the two
    keywords to be present in the text. Returns the action or None.
    """
    if not at_me:
        return None
    if _OPEN_KEYWORD in message_text and _CLOSE_KEYWORD not in message_text:
        return "open"
    if _CLOSE_KEYWORD in message_text and _OPEN_KEYWORD not in message_text:
        return "close"
    # Both keywords present: pick whichever appears first in the message.
    open_idx = message_text.find(_OPEN_KEYWORD)
    close_idx = message_text.find(_CLOSE_KEYWORD)
    if open_idx == -1 and close_idx == -1:
        return None
    if open_idx == -1:
        return "close"
    if close_idx == -1:
        return "open"
    return "open" if open_idx < close_idx else "close"


def extract_skill_name(response_text: str) -> Optional[str]:
    """Extract the skill name from the first non-blank line of an LLM reply.

    Expected first line shape: `[技能名] [成功|失败] - <独白>`
    Returns the skill name (without brackets) or None.
    """
    if not response_text:
        return None
    for raw in response_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _SKILL_LINE_RE.match(line)
        if match:
            return match.group(1).strip()
        return None
    return None


# Direction (清/混) is an INTERNAL state (spec §4.4.3) — LLM does NOT
# output it. The plugin detects direction by scanning text for keywords:
#   - sharp keywords (烟/烟草/雪茄/烟头/点火) → "清"
#   - hazy keywords (酒/威士忌/啤酒/红酒/药/Joy/草/大麻) → "混"
# When both classes appear, hazy wins (more conservative for drunk counting).

_SHARP_KEYWORDS: tuple[str, ...] = (
    "烟", "烟草", "雪茄", "烟头", "点火",
    "香烟", "点火器", "打火机", "点烟", "根烟",
)

_HAZY_KEYWORDS: tuple[str, ...] = (
    "酒", "威士忌", "啤酒", "红酒", "黄酒", "白酒",
    "药", "Joy", "joy", "草", "大麻", "嗑", "磕",
    "片", "粉", "白粉", "海洛因", "摇头丸", "冰毒",
    # NOTE: "海洛因/摇头丸/冰毒" are REAL drug names that should
    # never appear in the LLM reply per spec §4.4.5. But if the
    # keyword scan accidentally catches one, treat as hazy (safer
    # default — at least the drunk counter will fire correctly).
)


def infer_direction(text: str) -> Optional[Literal["清", "混"]]:
    """Infer the 食髓知味 direction (清/混) by scanning `text` for
    sharp vs hazy keywords. Used by main.py to:

      - Decide whether to bump drunk_count (`混` only).
      - Detect a direction transition (`清` ↔ `混`) for the state-
        transition banner.

    Returns None if neither class of keyword is found in `text`.
    Caller should fall back to the previous direction in that case
    (no transition).

    The function is **pure** — no regex, no LLM call, just substring
    checks. Caller passes either the user's message (priority) or the
    LLM reply (fallback); see `_resolve_direction(...)` in main.py.
    """
    if not text:
        return None
    has_hazy = any(kw in text for kw in _HAZY_KEYWORDS)
    has_sharp = any(kw in text for kw in _SHARP_KEYWORDS)
    if has_hazy and not has_sharp:
        return "混"
    if has_sharp and not has_hazy:
        return "清"
    if has_hazy and has_sharp:
        # Both classes present → hazy wins (more conservative: drunk
        # counter fires, harder to under-count).
        return "混"
    return None


# Matches the success/failure token only (group 2 of `_SKILL_LINE_RE`'s
# match). Used by spec §4.3's failure-rhythm logic in main.py.
def extract_outcome(response_text: str) -> Optional[Literal["成功", "失败"]]:
    """Return the success/failure token ("成功"/"失败") of the first
    non-blank line's lead bracket, or None if the line doesn't look like
    a skill output.

    Used by main.py to feed `state.record_outcome(...)`; a `[失败]`
    resets the failure streak, anything else increments it.
    """
    if not response_text:
        return None
    for raw in response_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _SKILL_LINE_RE.match(line)
        if m:
            return m.group(2)  # "成功" or "失败"
        return None
    return None


if __name__ == "__main__":
    # --- smoke tests for detect_toggle ---
    assert detect_toggle("芝麻开门", at_me=True) == "open"
    assert detect_toggle("芝麻关门", at_me=True) == "close"
    assert detect_toggle("芝麻开门", at_me=False) is None
    assert detect_toggle("芝麻关门", at_me=False) is None
    assert detect_toggle("今天天气不错", at_me=True) is None
    # mixed: close appears first
    assert detect_toggle("芝麻关门之后再芝麻开门,怎么样", at_me=True) == "close"

    # --- smoke tests for extract_skill_name ---
    assert extract_skill_name(
        "[食髓知味] [成功] - 今天你该来一杯。\n\n说起来,我口袋里有半瓶没喝完的..."
    ) == "食髓知味"
    assert extract_skill_name(
        "\n\n  [逻辑思维] [失败] - 这推理站不住脚。\n\n是吗?"
    ) == "逻辑思维"
    assert extract_skill_name("今天是个好日子,适合不办任何案子。") is None
    assert extract_skill_name("") is None

    # all 12 skills recognized
    for skill in (
        "逻辑思维", "博学多闻", "能说会道", "见微知著",
        "内陆帝国", "通情达理", "争强好胜", "平心定气",
        "食髓知味", "天人感应", "疑神疑鬼", "五感发达",
    ):
        resp = f"[{skill}] [成功] - \"...\"\n\n本体对话,无前缀,直接写。"
        assert extract_skill_name(resp) == skill, f"Failed for {skill}"

    # --- smoke tests for infer_direction ---
    assert infer_direction("我想点根烟") == "清"
    assert infer_direction("再来一杯威士忌") == "混"
    assert infer_direction("喝完威士忌再来根烟") == "混"  # hazy wins
    assert infer_direction("今天天气真好") is None
    assert infer_direction("") is None

    # --- smoke tests for extract_outcome ---
    assert extract_outcome("[食髓知味] [成功] - 今晚你该来一杯。") == "成功"
    assert extract_outcome("[食髓知味] [失败] - 不,该停。") == "失败"
    assert extract_outcome("今天是个好日子。") is None
    assert extract_outcome("") is None

    print("All smoke tests passed.")
