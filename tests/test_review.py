import unittest
from types import SimpleNamespace

from shippy.git import PullRequestContext
from shippy.github import COMMENT_MARKER
from shippy.review import (
    build_review_prompt,
    failure_body,
    normalize_review,
    pending_body,
)


class ReviewTest(unittest.TestCase):
    def test_prompt_override_uses_configured_template(self) -> None:
        context = PullRequestContext(
            base="main",
            branch="feat/x",
            commits="abc change",
            stat="file.py | 1 +",
            name_status="M\tfile.py",
            diff="diff --git a/file.py b/file.py",
            trimmed=False,
        )
        pr = SimpleNamespace(
            title="feat: x",
            url="https://github.com/acme/repo/pull/1",
            body="body",
        )

        prompt = build_review_prompt(
            context,
            pr,
            "custom {{pr_title}} {{changed_files}} {{trim_note}}",
            "extra review rule",
        )

        self.assertEqual(
            prompt,
            "custom feat: x M\tfile.py Use the available review notes and diff context.\n\n"
            "Extra instructions:\nextra review rule\n",
        )

    def test_default_prompt_mentions_trimmed_diff(self) -> None:
        context = PullRequestContext(
            base="main",
            branch="feat/x",
            commits="abc change",
            stat="file.py | 1 +",
            name_status="M\tfile.py",
            diff="diff --git a/file.py b/file.py",
            trimmed=True,
        )
        pr = SimpleNamespace(title="feat: x", url="https://example.test/pr/1", body="body")

        prompt = build_review_prompt(context, pr)

        self.assertIn("Some diff context was truncated", prompt)
        self.assertIn("PR title: feat: x", prompt)
        self.assertIn("Changed files:\nM\tfile.py", prompt)
        self.assertIn("Diff:\ndiff --git a/file.py b/file.py", prompt)

    def test_normalize_review_strips_outer_fence(self) -> None:
        review = normalize_review(
            """```markdown
### Verdict
✅ Pass: ok
```"""
        )

        self.assertTrue(review.startswith(f"{COMMENT_MARKER}\n## AI Review"))
        self.assertNotIn("```markdown", review)

    def test_status_bodies_include_marker(self) -> None:
        self.assertIn(COMMENT_MARKER, pending_body())
        self.assertIn(COMMENT_MARKER, failure_body("boom"))


if __name__ == "__main__":
    unittest.main()
