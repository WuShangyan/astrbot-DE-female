"""Banner rendering for the AstrBot Vivian Vale plugin.

Five banner types share the same ASCII frame (`░▒▓` + 66 `█` + `▓▒░`):
  - Open (DE mode activation, fixed 复仇女神 epigraph)
  - Close (DE mode deactivation, epigraph chosen by last skill)
  - Clear / Haze (state-transition on direction change to 清/混)
  - Voice-bleed (DE-OFF spontaneous leak, no divider, no >>>)

Plus `render_sleep_banner` for the 04:00-08:00 sleep window (no frame).
"""

from __future__ import annotations

from epigraphs import get_epigraph

# ---------------------------------------------------------------------------
# Shared frame constants
# ---------------------------------------------------------------------------

_TOP_BAR = "░▒▓" + "█" * 66 + "▓▒░"
_DIVIDER = "-" * 72

_OPEN_STATUS = "  >>> 二十四个声音正在门后争吵... 黑暗里有什么正在涌动..."
_CLOSE_STATUS = "  >>> 舞台灯光熄灭。幕布落下。声音们沉沉睡去..."

# Vivian's reaction lines for the voice-bleed body. Cold, dismissive — she
# never acknowledges the leak.
_VOICE_BLEED_BODY_LINES: tuple[str, ...] = (
    "她没听见。",
    "她没理。",
    "她回过神。",
    "……走神了。",
    "（压了压帽檐。）",
    "……嗯。",
)


# ---------------------------------------------------------------------------
# Internal renderer for framed banners
# ---------------------------------------------------------------------------

def _render(epigraph_body: str, status_line: str) -> str:
    """Render the canonical frame: top bar, epigraph body, divider, status, bottom bar."""
    return (
        f"{_TOP_BAR}\n"
        f"\n"
        f"{epigraph_body}\n"
        f"\n"
        f"{_DIVIDER}\n"
        f"{status_line}\n"
        f"{_TOP_BAR}"
    )


# ---------------------------------------------------------------------------
# Public banner functions
# ---------------------------------------------------------------------------

def render_open_banner() -> str:
    """Banner shown after `芝麻开门`. Fixed opening epigraph."""
    return _render(get_epigraph(None), _OPEN_STATUS)


def render_close_banner(last_skill: str | None) -> str:
    """Banner shown after `关门`. Epigraph chosen by `last_skill`; falls back
    to opening epigraph if `last_skill` is None or not in the table."""
    return _render(get_epigraph(last_skill), _CLOSE_STATUS)


def render_clear_banner() -> str:
    """State-transition banner when entering `[清]` direction. Same frame
    as open/close, but body is the cigarettes quote."""
    body = (
        "            凌晨三点点的那根烟，比任何证词都亮。\n"
        "          清醒的人 — 是看得见黑影的那种。"
    )
    status = "  >>> 一根烟点亮了——二十四个声音都看见了黑影。"
    return _render(body, status)


def render_haze_banner() -> str:
    """State-transition banner when entering `[混]` direction."""
    body = (
        "            那瓶威士忌见底的时候，镜里只剩影子，没有名字。\n"
        "          醉了的人 — 是连自己都不认识的那几分钟。"
    )
    status = "  >>> 那二十四个声音散成一片雾——谁是谁，全乱了。"
    return _render(body, status)


def render_voice_bleed_banner(
    skill_name: str,
    sample_line: str,
    body_line: str,
) -> str:
    """Banner emitted when DE is OFF but a skill leaks through (spec §4.4.7b).

    Format: `░▒▓ frame / 〔<skill_name>〕<sample_line> / <body_line> / ░▒▓ frame`.
    No divider, no `>>>` status, no epigraph — this is a leak, not a state change.
    """
    return (
        f"{_TOP_BAR}\n"
        f"\n"
        f"  〔{skill_name}〕{sample_line}\n"
        f"\n"
        f"  {body_line}\n"
        f"\n"
        f"{_TOP_BAR}"
    )


def render_sleep_banner() -> str:
    """Banner shown when the sleep window (04:00-08:00) auto-closes DE.
    No frame — just a sleepy line plus the deactivation hint."""
    return (
        "[四点了。睡觉。声音们也该安静了。]\n"
        "✧ Voices dimming. Vivian rests. Resuming at 08:00."
    )


# ---------------------------------------------------------------------------
# Smoke tests (run via `python3 banners.py`)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _TOP_BAR_LOCAL = "░▒▓" + "█" * 66 + "▓▒░"
    _DIVIDER_LOCAL = "-" * 72

    _failures: list[str] = []

    def _assert(condition: bool, label: str) -> None:
        if not condition:
            _failures.append(label)
            print(f"  FAIL  {label}")
        else:
            print(f"  PASS  {label}")

    # --- open banner ----------------------------------------------------
    b = render_open_banner()
    _assert(b.startswith(_TOP_BAR_LOCAL), "open banner starts with top bar")
    _assert(b.rstrip().endswith(_TOP_BAR_LOCAL), "open banner ends with top bar")
    _assert("复仇女神就在家中的镜子里" in b, "open banner contains 复仇女神 epigraph")
    _assert(">>> 二十四个声音正在门后争吵" in b, "open banner contains open status line")
    _assert(_DIVIDER_LOCAL in b, "open banner contains divider")

    # --- close banner ---------------------------------------------------
    b = render_close_banner("食髓知味")
    _assert(b.startswith(_TOP_BAR_LOCAL), "close banner starts with top bar")
    _assert(b.rstrip().endswith(_TOP_BAR_LOCAL), "close banner ends with top bar")
    _assert("醉于酒" in b, "close banner uses 食髓知味 epigraph when skill is 食髓知味")
    _assert("复仇女神" not in b, "close banner does NOT use opening epigraph when skill known")
    _assert(">>> 舞台灯光熄灭" in b, "close banner contains close status line")

    b = render_close_banner(None)
    _assert("复仇女神" in b, "close banner falls back to opening epigraph when skill is None")

    b = render_close_banner("不存在的技能")
    _assert("复仇女神" in b, "close banner falls back to opening epigraph for unknown skill")

    # --- clear / haze transition banners --------------------------------
    cb = render_clear_banner()
    _assert(cb.startswith(_TOP_BAR_LOCAL) and cb.rstrip().endswith(_TOP_BAR_LOCAL),
            "clear banner has frame")
    _assert("凌晨三点点的那根烟" in cb, "clear banner contains cigarettes quote")
    _assert(">>> 一根烟点亮了" in cb, "clear banner contains clear status line")
    _assert(_DIVIDER_LOCAL in cb, "clear banner contains divider")
    _assert("复仇女神" not in cb, "clear banner does NOT use opening epigraph")

    hb = render_haze_banner()
    _assert(hb.startswith(_TOP_BAR_LOCAL) and hb.rstrip().endswith(_TOP_BAR_LOCAL),
            "haze banner has frame")
    _assert("威士忌见底" in hb, "haze banner contains whisky quote")
    _assert(">>> 那二十四个声音散成一片雾" in hb, "haze banner contains haze status line")
    _assert(_DIVIDER_LOCAL in hb, "haze banner contains divider")
    _assert("复仇女神" not in hb, "haze banner does NOT use opening epigraph")

    # --- voice-bleed banner ---------------------------------------------
    vb = render_voice_bleed_banner("食髓知味", "再点一根。", "她没听见。")
    _assert(vb.startswith(_TOP_BAR_LOCAL), "voice-bleed banner starts with top bar")
    _assert(vb.rstrip().endswith(_TOP_BAR_LOCAL), "voice-bleed banner ends with top bar")
    _assert("食髓知味" in vb, "voice-bleed banner includes skill name")
    _assert("再点一根。" in vb, "voice-bleed banner includes sample line")
    _assert("她没听见。" in vb, "voice-bleed banner includes body line")
    _assert("[成功]" not in vb and "[失败]" not in vb,
            "voice-bleed banner does NOT include [成功]/[失败] tags")
    _assert(_DIVIDER_LOCAL not in vb, "voice-bleed banner does NOT include divider")
    _assert("复仇女神" not in vb, "voice-bleed banner does NOT include opening epigraph")
    _assert(">>>" not in vb, "voice-bleed banner does NOT include >>> status line")

    # --- summary --------------------------------------------------------
    print()
    if _failures:
        print(f"FAILED: {len(_failures)} test(s): {', '.join(_failures)}")
        raise SystemExit(1)
    else:
        print("All banner smoke tests passed.")
