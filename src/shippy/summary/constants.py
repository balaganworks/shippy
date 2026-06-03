"""Summary prompt constants."""

from __future__ import annotations

DEFAULT_TITLE_PREFIXES = ["feat:", "task:", "fix:", "hotfix:", "chore:", "docs:", "refactor:"]

DEFAULT_GROUP_PROMPT_TEMPLATE = """Summarize one area of a GitHub PR.

Return plain text notes only. These notes are internal context for the final PR description.

Use this loose note shape:
Area: {{area}}
Summary: one sentence, 18 words max
Important changes:
- 2-4 concise bullets max
Significant files:
- up to 4 changed paths with why they matter
Validation signals:
- only checks visible in the diff
Risk signals:
- only meaningful risks visible in this area

Rules:
- Be specific to this area.
- Mention tests, rollout, production impact, or validation only when visible in the diff.
- Prefer implemented behavior, contracts, data shape, migrations, and workflows over file lists.
- Write in past tense. Focus on changed behavior.
- If a section has no real items, omit it.
- Be concise but detailed enough that a reviewer can route attention.
- Use short bullets.
- Include meaningful risks only when visible.

PR branch: {{branch}}
Base branch: {{base}}

Ignored paths:
{{ignored_paths}}

Files in this area:
{{files}}

Area diff:
{{diff}}
"""

DEFAULT_FINAL_PROMPT_TEMPLATE = """Write final GitHub PR metadata from the source context below.

Return this exact plain-text shape:
{{title_shape}}BODY:
## Summary
- 2-4 one-line bullets

Important:
- Return plain Markdown text.
- Follow the output shape exactly.
- After BODY:, write the full PR description Markdown.
- Every section heading must be level 2 Markdown: `## Heading`.
- Use only these sections, in this order when useful:
  Summary, Key Changes, Significant Files, Validation, Risk, Reviewer Notes, Deep Dive.
- Include sections only when they have real content.
- Keep Summary to 2-4 bullets, one line each.
- All section content must be Markdown bullets.
- Write in past tense. Focus on implemented changes.
- Use concrete content instead of filler like "None", "N/A", "Unknown", "Pending", or "TBD".
- Keep each fact in the most relevant section.
- Use simple flat bullets.
{{title_rules}}

Input data for writing the PR body:

Commit messages from this branch:
{{commits}}

Changed files summary from git diff stat:
{{stat}}

Grouped summaries from the earlier summary step:
{{area_summaries}}
"""
