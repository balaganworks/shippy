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

Return short Markdown notes.

Shape:
### {{area}}
Verdict: Pass or Fail
Findings:
- For Pass, write exactly `{{no_blocking_issues}}`
- For Fail, write 1-3 fix bullets with path, visible line if available, bug, and fix direction.
Tests:
- Mention visible tests or write `{{no_validation_visible}}`

Rules:
- Review concrete bugs, security issues, data-loss risks, broken contracts,
  and meaningful performance issues.
- Prefer Pass for weak or speculative concerns.
- Be blunt, concise, and actionable.
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

DEFAULT_REVIEW_FINAL_PROMPT_TEMPLATE = f"""Write a concise GitHub PR review.

Use the review notes and diff below as source context.

Return Markdown only.

Pass shape:
{AI_REVIEW_HEADING}

### Verdict
✅ Pass: one short reason.

Fail shape:
{AI_REVIEW_HEADING}
### Verdict
❌ Failed: one short reason.

### Findings
- 1-5 fix bullets max.

### Tests
- Visible validation, or `{NO_VALIDATION_VISIBLE}`

Rules:
- If pass, write only Verdict and one short Tests section.
- If fail, write Verdict, Findings, and Tests.
- Deduplicate overlapping area findings.
- Prefer Pass over weak speculation.
- Be blunt, concise, and actionable.
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

Diff:
{{{{diff}}}}
"""
