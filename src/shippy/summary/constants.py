"""Summary prompt constants."""

from __future__ import annotations

DEFAULT_TITLE_PREFIXES = ["feat:", "task:", "fix:", "hotfix:", "chore:", "docs:", "refactor:"]

DEFAULT_GROUP_PROMPT_TEMPLATE = """Summarize this PR area.

Output notes:
Area: {{area}}
Summary: one short sentence
Important changes:
- 2-4 bullets
Significant files:
- up to 4 changed paths with why they matter
Validation signals:
- visible checks/tests only
Risk signals:
- meaningful visible risks only

Write past tense. Focus on behavior, contracts, data shape, workflows, and validation.
Omit empty sections. Keep bullets short.

PR branch: {{branch}}
Base branch: {{base}}

Ignored paths:
{{ignored_paths}}

Files in this area:
{{files}}

Area diff:
{{diff}}
"""

DEFAULT_FINAL_PROMPT_TEMPLATE = """Write GitHub PR metadata.

Output:
{{title_shape}}BODY:
## Summary
- 2-4 bullets

After BODY:, write Markdown with level 2 headings and flat bullets.
Use useful sections from:
Summary, Key Changes, Significant Files, Validation, Risk, Reviewer Notes, Deep Dive.
Write past tense. Keep concrete facts. Omit empty sections.
{{title_rules}}

Commits:
{{commits}}

Diff stat:
{{stat}}

Area summaries:
{{area_summaries}}
"""
