# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Vivian Vale AstrBot Plugin

A AstrBot "Star" plugin that gives a chat bot the persona of **Vivian Vale** — an amnesiac hardboiled female detective from the Disco Elysium universe. The plugin has two layers:

- **Base persona** (always on): `personas/persona_base.md` — identity, voice, boundaries.
- **DE layer** (toggled on with `芝麻开门`): `personas/persona_de.md` + 24 "skill voices" that periodically take over the reply.

A `VivianVale` class is registered as an AstrBot `Star` in `main.py`. AstrBot is the runtime; this repo is a plugin loaded by it. There is no separate build/lint/test runner — AstrBot imports the module directly.

## Layout

```
main.py          VivianVale Star class, event/hook handlers, LLM injection
state.py         StateStore dataclass (in-memory, single-session)
parsing.py       Pure helpers: detect_toggle, extract_skill_name, infer_direction, extract_outcome
banners.py       Banner string renderers (toggle/sleep/failure)
epigraphs.py     Skill-idle whisper strings, organized by category
personas/        persona_base.md + persona_de.md (Chinese prose)
skills/          24 skill dirs + 2 metadata dirs (see below)
metadata.yaml    AstrBot plugin manifest
plugin.json      AstrBot plugin manifest (older/duplicate)
```

### `skills/` directory

One subdirectory per skill, each containing a single `SKILL.md` with YAML frontmatter (`name:`, `description:`, optional `disable-model-invocation:`) and a body that starts at the first `# ` heading. Skill IDs are English (`logic`, `rhetoric`, `shivers`, …); the body title carries the Chinese name (e.g. `# 逻辑思维 [智力系]`).

Two directories in `skills/` are **not** 24-skill content and are skipped at load time (constant `_SKILL_DIR_SKIP` in `main.py`):
- `skills/de-toggle/` — toggle command spec & 24-skill manifest table.
- `skills/skills/` — the user-facing `/disco-elysium:skills` help page.

The full 24-skill mapping (Chinese ↔ English) is enumerated in `skills/de-toggle/SKILL.md` and mirrored in `epigraphs.SKILL_EPIGRAPHS`.

## Runtime architecture (the "9 Duties")

`main.py` is organized by numbered duties. Read in this order to understand the data flow:

1. **Toggle** — `@filter.command("芝麻开门")` / `"关门"` flips `state.de_enabled` (sleep window 04:00–08:00 blocks `open`).
2. **Pre-LLM gate** — `@filter.event_message_type(ALL, priority=1)` runs *before* the LLM pipeline: enforces sleep window auto-close, drops group messages not @-mentioning the bot, infers 食髓知味 direction (清/混) by keyword scan, and may fire a "voice bleed" (DE-off spontaneous whisper) via LLM.
3. **Persona injection** — `@filter.on_llm_request()` writes the **static** DE layer (persona_de + 24 skill bodies, joined once at `initialize()`) into `req.system_prompt`; **dynamic** state (drunk, failure hint/force, direction) goes into `req.extra_user_content_parts` with `.mark_as_temp()` so it doesn't accumulate across turns.
4. **Failure rhythm** — `@filter.on_llm_response()` calls `extract_outcome()` on the reply. A `[失败]` resets the streak; ≥5 successive non-failures nudges a hint, ≥8 forces failure. The forced signal is delivered next turn via `extra_user_content_parts` (`[VIVIAN_FAILURE:FORCE]`).
5. **Identity scrub + length cap** — `@filter.on_decorating_result()` rewrites Plain text components: replaces identity-leaking keywords (GPT/Claude/AI/.../"Garrett"→"那个人") with `████` or "那个人"; truncates replies >500 chars.

Background task: `_silence_check_loop` runs every 30 min, proactively pushes a "silence bleed" monologue to any conversation that has been idle ≥12 h (5-day global cooldown).

## Conventions & gotchas

- **State is in-memory only** (no persistence); `StateStore` is not thread-safe. Cancellation of the silence task is handled in `dispose()`.
- **No external deps in `parsing.py` / `state.py`** — they import only stdlib. `main.py` is the only file importing `astrbot.*`. Keep parsing pure for unit-testability.
- **Smoke tests live inside the modules** as `if __name__ == "__main__":` blocks. Run them directly:
  - `python3 parsing.py` — covers `detect_toggle`, `extract_skill_name`, `infer_direction`, `extract_outcome`.
  - `python3 state.py` — covers drunk counter, sleep window, daily reset, failure streak, direction cache, voice-bleed gates.
  - `python3 banners.py` — visual smoke (prints banners).
  No pytest, no CI. There is no single-test runner beyond running the whole file.
- **Python 3.10+ syntax** is used (`str | None`, `Literal[...]`, `match` not used). `main.py` will not parse on 3.9.
- **Toggle command requires `@bot`** in groups; `detect_toggle()` enforces this. The `芝麻开门`/`关门` `@filter.command` handlers do not — they accept the keyword in any message that reaches them. In groups this is filtered upstream by the `@`-check in `on_message`.
- **Skill name is the LLM's job, not the parser's.** `extract_skill_name()` only verifies the *first* non-blank line matches `[中文名] [成功|失败]`; it does not look up the ID. The `cn_to_id` map in `main.py` is built once from SKILL.md titles and used to feed skill bodies into the system prompt.
- **Direction (清/混) is internal state only.** The LLM never outputs it; the plugin scans user/reply text for sharp (烟/...) vs hazy (酒/...) keywords. Hazy wins on conflict (drunk counter is conservative).
- **`Garrett` → `那个人` is in the identity scrub list** for a reason: the persona hides that name until the player earns it. Don't remove this.
- **Skill-name matching is exact Chinese** (e.g. `食髓知味`, not `electrochemistry`). The 12-skill smoke test in `parsing.py` lists the 12 it knows; the other 12 (authority, encyclopedia, rhetoric, drama, conceptualization, visual-calculus, volition, empathy, suggestion, endurance, pain-threshold, physical-instrument, electrochemistry, half-light, hand-eye, perception, reaction-speed, savoir-faire, interfacing, composure, shivers) are covered indirectly by the directory iteration in `_load_skill_bodies`.

## Common edits

- **Tweak a persona trait** → edit `personas/persona_base.md` (always on) or `personas/persona_de.md` (DE mode).
- **Add/edit a skill voice** → edit `skills/<skill_id>/SKILL.md`. The body is loaded at `initialize()` and concatenated into `_de_system_prompt`; restart AstrBot to pick up changes.
- **Change a banner string** → `banners.py`. Keep the `render_voice_bleed_banner(sample, body)` signature stable — the only one called with two args (not currently invoked from `main.py`; reserved for the legacy bleed path).
- **Add a new gate** (e.g. a new cooldown) → add the field + method to `StateStore` in `state.py`; add a smoke-test case in the `if __name__ == "__main__":` block; call it from the appropriate Duty in `main.py`.
- **Adjust the LLM reply format** → the parser regex `_SKILL_LINE_RE` in `parsing.py` is the contract; any change to the leading `[名字] [成功/失败]` shape must update both the regex and the persona docs in `personas/persona_de.md`.

## Manifests

- `metadata.yaml` and `plugin.json` carry the same identity (`name: vivian-vale`, version, author, homepage). Update both if bumping the version.
- AstrBot discovers the plugin via `@register_star` on `VivianVale` in `main.py` — renaming the class or module requires updating AstrBot's plugin loader config.
