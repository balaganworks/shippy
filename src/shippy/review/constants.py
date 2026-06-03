"""Review prompt constants."""

from __future__ import annotations

COMMENT_MARKER = "<!-- shippy-review -->"
AI_REVIEW_HEADING = "## AI Review"
NO_BLOCKING_ISSUES = "- No blocking issues found."
NO_VALIDATION_VISIBLE = "- No validation visible in PR context."
UNKNOWN_FAILURE = "unknown failure"

REVIEW_PENDING_BODY = f"""{COMMENT_MARKER}
{AI_REVIEW_HEADING}

### Verdict
⏳ Running: AI review in progress.
"""

REVIEW_FAILURE_BODY_TEMPLATE = f"""{COMMENT_MARKER}
{AI_REVIEW_HEADING}

### Verdict
❌ Failed: AI review did not complete.

### Error
```text
{{reason}}
```
"""

DEFAULT_REVIEW_GROUP_PROMPT_TEMPLATE = """Review one area of a GitHub PR.

Return Markdown only. No YAML. No JSON. No code fence wrapping the whole answer.

Required shape:
### {{area}}

Findings:
- If pass: write exactly `{{no_blocking_issues}}`
- If failed: write 1-3 actionable findings.
- Each finding must include:
  - changed file path
  - relevant line or small line range if visible
  - what breaks
  - exact fix direction

Tests:
- Mention only tests or validation visible in this area diff.
- If none visible, write `{{no_validation_visible}}`

Notes:
- 1-3 bullets with source-of-truth, risk, edge case, or follow-up context.
- No generic advice.

Rules:
- Review only concrete bugs, security issues, data-loss risks,
  broken contracts, or meaningful performance issues introduced by the diff.
- Prefer pass over weak speculation.
- Be blunt, concise, and actionable.
- Do not praise.
- Do not include a table.
- Refer only to changed files and relevant sources.
- {{trim_note}}

PR title: {{pr_title}}
PR URL: {{pr_url}}
Branch: {{branch}}
Base branch: {{base}}

PR description:
{{pr_body}}

Commits:
{{commits}}

Diff stat:
{{stat}}

Files in this area:
{{files}}

Area diff:
{{diff}}
"""

DEFAULT_REVIEW_FINAL_PROMPT_TEMPLATE = f"""Write a GitHub PR review.

Use the area review notes below as source context.

Return Markdown only. No YAML. No JSON. No code fence wrapping the whole answer.

Required shape:
{AI_REVIEW_HEADING}

### Verdict
✅ Pass: one short reason

or

### Verdict
❌ Failed: one short reason

### Summary
- 2-4 bullets max.
- Each bullet must be short and concrete.

### Findings
- If all area findings passed: write exactly `{NO_BLOCKING_ISSUES}`
- If failed: write the strongest 1-5 actionable findings.

### Tests
- Mention only tests or validation visible in PR context.
- If none visible, write `{NO_VALIDATION_VISIBLE}`

### Reviewer Notes
- 1-4 bullets with source-of-truth, risk, edge case, or follow-up context.
- No generic advice.

Rules:
- Deduplicate overlapping area findings.
- Prefer Pass over weak speculation.
- Be blunt, concise, and actionable.
- Do not praise.
- Do not include a table.
- {{{{trim_note}}}}

PR title: {{{{pr_title}}}}
PR URL: {{{{pr_url}}}}
Branch: {{{{branch}}}}
Base branch: {{{{base}}}}

PR description:
{{{{pr_body}}}}

Commits:
{{{{commits}}}}

Diff stat:
{{{{stat}}}}

Changed files:
{{{{changed_files}}}}

Area reviews:
{{{{area_reviews}}}}
"""
