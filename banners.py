"""Banner rendering for the AstrBot Vivian Vale plugin.

Renders 4 banner types:
  - Toggle on/off (DE mode activation and deactivation)
  - Sleep auto-close (sleeping beauties)
  - Voice bleed (DE-off occasional leak)
  - Failure hints and forced failures
"""

from __future__ import annotations


def render_toggle_on_banner() -> str:
    """Return the banner shown after ``@bot 芝麻开门``."""
    return "✦ 24 voices awakened. They remember what you've forgotten."


def render_toggle_off_banner() -> str:
    """Return the banner shown after ``@bot 芝麻关门``."""
    return "✧ The voices fall silent. Vivian Vale remains."


def render_sleep_banner() -> str:
    """Return the banner shown when the sleep window (04:00-08:00) activates."""
    return (
        "[四点了。睡觉。声音们也该安静了。]\n"
        "✧ Voices dimming. Vivian rests. Resuming at 08:00."
    )


def render_voice_bleed_banner(sample: str, body: str) -> str:
    """Return a voice-bleed banner (DE-off occasional leak).

    Args:
        sample: A skill sample line (e.g. from ``skills/{id}/SKILL.md``).
        body: Vivian's reaction line.

    Returns:
        A formatted banner wrapping the sample and body lines.
    """
    return f"[{sample}]\n{body}"


def render_failure_hint(skill_name: str) -> str:
    """Return a whisper hint that the LLM should consider a failure.

    Args:
        skill_name: The name of the skill that failed.

    Returns:
        A whisper string in the form ``[……不太对。{skill_name}低声说。]``.
    """
    return f"[……不太对。{skill_name}低声说。]"


def render_force_failure(skill_name: str) -> str:
    """Return a forced-failure message for the given skill.

    Args:
        skill_name: The name of the skill that failed.

    Returns:
        A string in the form ``[失败。{skill_name}不说话了。]``.
    """
    return f"[失败。{skill_name}不说话了。]"


# ---------------------------------------------------------------------------
# Visual verification when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Toggle ON ===")
    print(render_toggle_on_banner())
    print()

    print("=== Toggle OFF ===")
    print(render_toggle_off_banner())
    print()

    print("=== Sleep Banner ===")
    print(render_sleep_banner())
    print()

    print("=== Voice Bleed ===")
    print(
        render_voice_bleed_banner(
            "她记得一个声音——逻辑的声音——在她耳边说：世界是一道数学题。",
            "……嗯。",
        )
    )
    print()

    print("=== Failure Hint ===")
    print(render_failure_hint("食髓知味"))
    print()

    print("=== Force Failure ===")
    print(render_force_failure("逻辑思维"))
