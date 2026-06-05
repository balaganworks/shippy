"""Review prompt constants."""

from __future__ import annotations

COMMENT_MARKER = "<!-- shippy-review -->"
AI_REVIEW_HEADING = "## AI Review"
REVIEW_VERDICT_HEADING = "### Verdict"
REVIEW_FINDINGS_HEADING = "### Findings"
REVIEW_PASS_PREFIX = "✅ Pass"
REVIEW_FAILED_PREFIX = "❌ Failed"
REVIEW_RESULT_PREFIXES = (REVIEW_PASS_PREFIX, REVIEW_FAILED_PREFIX)
NO_BLOCKING_ISSUES = "- No blocking issues found."
NO_VALIDATION_VISIBLE = "- No validation visible in PR context."
UNKNOWN_FAILURE = "unknown failure"
NO_REVIEW_TEXT = "- No review text returned."
UNSTRUCTURED_REVIEW_REASON = "❌ Failed: review output was incomplete."
CONTEXT_ESCAPE_PHRASES = (
    "provide the specific file",
    "exact changes you want me to review",
    "provide more context",
)
UNSTRUCTURED_REVIEW_TEMPLATE = f"""{REVIEW_VERDICT_HEADING}
{UNSTRUCTURED_REVIEW_REASON}

{REVIEW_FINDINGS_HEADING}
{{review_text}}
"""

REVIEW_PENDING_BODY = f"""{COMMENT_MARKER}
{AI_REVIEW_HEADING}

{REVIEW_VERDICT_HEADING}
⏳ Running: AI review in progress.
"""

REVIEW_FAILURE_BODY_TEMPLATE = f"""{COMMENT_MARKER}
{AI_REVIEW_HEADING}

{REVIEW_VERDICT_HEADING}
{REVIEW_FAILED_PREFIX}: AI review did not complete.

### Error
```text
{{reason}}
```
"""

DEFAULT_REVIEW_GROUP_PROMPT_TEMPLATE = """Review this PR area.

Output:
### {{area}}
Verdict: Pass or Fail
Findings:
- Pass: write `{{no_blocking_issues}}`
- Fail: 1-3 bullets like `path: bug -> fix`.
Tests:
- Visible validation, or write `{{no_validation_visible}}`

Focus on real bugs, security, data loss, broken contracts, and meaningful perf.
Prefer Pass when uncertain. Keep bullets small and actionable.
{{trim_note}}

PR title: {{pr_title}}

Files in this area:
{{files}}

Area diff:
{{diff}}
"""

DEFAULT_REVIEW_FINAL_PROMPT_TEMPLATE = f"""Write a concise GitHub PR review.

Output Markdown:
{AI_REVIEW_HEADING}
### Verdict
Choose one:
✅ Pass: short reason.
❌ Failed: short reason.
### Findings
- only for Failed; 1-5 bullets like `path: bug -> fix`
### Tests
- visible validation, or `{NO_VALIDATION_VISIBLE}`

Use Failed only for concrete blocking issues from the context.
Otherwise use Pass. Deduplicate findings. Keep it short.
{{{{trim_note}}}}

PR: {{{{pr_title}}}}

Changed files:
{{{{changed_files}}}}

Review context:
{{{{review_context}}}}
"""
