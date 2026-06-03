"""Prompt template helpers."""

from __future__ import annotations

from shippy.constants import EXTRA_INSTRUCTIONS_HEADING


def render_prompt(template: str, values: dict[str, str]) -> str:
    text = template
    for key, value in values.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def append_extra_instructions(prompt: str, extra_instructions: str) -> str:
    extra = extra_instructions.strip()
    if not extra:
        return prompt
    return f"{prompt.rstrip()}\n\n{EXTRA_INSTRUCTIONS_HEADING}\n{extra}\n"
