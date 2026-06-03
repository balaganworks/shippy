"""Summary prompt constants."""

from __future__ import annotations

DEFAULT_TITLE_PREFIXES = ["feat:", "task:", "fix:", "hotfix:", "chore:", "docs:", "refactor:"]

GROUP_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "area": {"type": "string"},
        "summary": {"type": "string"},
        "important_changes": {"type": "array", "items": {"type": "string"}},
        "significant_files": {"type": "array", "items": {"type": "string"}},
        "validation_signals": {"type": "array", "items": {"type": "string"}},
        "risk_signals": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "area",
        "summary",
        "important_changes",
        "significant_files",
        "validation_signals",
        "risk_signals",
    ],
}

DEFAULT_GROUP_PROMPT_TEMPLATE = """Summarize one area of a GitHub PR.

Return one JSON object with this shape:
{
  "area": "{{area}}",
  "summary": "one sentence, 18 words max",
  "important_changes": ["2-4 concise bullets max"],
  "significant_files": ["up to 4 important changed paths with why they matter"],
  "validation_signals": ["only checks visible in the diff"],
  "risk_signals": ["only meaningful risks visible in this area"]
}

Rules:
- Be specific to this area.
- Return JSON only. No Markdown fences. No prose before or after JSON.
- Do not invent tests, rollout, production impact, or validation.
- Prefer implemented behavior, contracts, data shape, migrations, and workflows over file lists.
- Write in past tense. Explain what changed, not tasks still to do.
- If a list has no real items, return an empty list.
- Be concise but detailed enough that a reviewer can route attention.

PR branch: {{branch}}
Base branch: {{base}}

Ignored paths:
{{ignored_paths}}

Files in this area:
{{files}}

Area diff:
{{diff}}
"""

DEFAULT_FINAL_PROMPT_TEMPLATE = """Write final GitHub PR metadata from area summaries.

Return this exact plain-text shape:
{{title_shape}}BODY:
## Summary
...

Important:
- If TITLE is requested, the first non-empty line must start with TITLE:.
- After BODY:, write the full PR description Markdown.
- Keep Summary to 2-4 bullets, one line each.
- Use this section order when supported:
  Summary, Key Changes, Significant Files, Validation, Risk, Reviewer Notes, Deep Dive.
- Do not add empty, generic, or ceremonial sections.
- Write in past tense. Explain implemented changes, not tasks still to do.
- Validation must mention only actual validation signals from summaries.
- Do not include unchecked task lists.
- Avoid "None", "N/A", "Unknown", "Pending", or "TBD" filler.
{{title_rules}}

PR branch: {{branch}}
Base branch: {{base}}

Commits:
{{commits}}

Diff stat:
{{stat}}

Area summaries:
{{area_summaries}}
"""
