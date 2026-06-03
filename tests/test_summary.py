import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from shippy.config import SummaryConfig, TitleConfig
from shippy.summary import (
    SummaryContext,
    SummaryGroup,
    build_final_prompt,
    build_group_prompt,
    clean_summary_body,
    collect_summary_context,
    group_summary_text,
    parse_name_status,
    parse_summary_result,
    split_groups,
)
from shippy.workflow import context_ready_message, single_group_message


class SummaryTest(unittest.TestCase):
    def test_group_prompt_override_uses_configured_template(self) -> None:
        context = SummaryContext(
            base="main",
            branch="feat/x",
            commits="abc change",
            stat="file.py | 1 +",
            ignores=["dist/**"],
            groups=[],
        )
        group = SummaryGroup(
            name="src",
            paths=["src/file.py"],
            diff="diff --git a/src/file.py b/src/file.py",
            trimmed=False,
        )

        prompt = build_group_prompt(
            context,
            group,
            "group {{area}} {{files}}",
            "extra nuance",
        )

        self.assertEqual(prompt, "group src - src/file.py\n\nExtra instructions:\nextra nuance\n")

    def test_final_prompt_override_uses_configured_template(self) -> None:
        context = SummaryContext(
            base="main",
            branch="feat/x",
            commits="abc change",
            stat="file.py | 1 +",
            ignores=[],
            groups=[],
        )

        prompt = build_final_prompt(
            context,
            ["### src"],
            "final {{branch}} {{area_summaries}} {{title_prefixes}}",
            "extra nuance",
            TitleConfig(update=True, enforce_prefix=True, prefixes=["feat:", "fix:"]),
        )

        self.assertEqual(
            prompt, "final feat/x ### src feat:, fix:\n\nExtra instructions:\nextra nuance\n"
        )

    def test_default_prompts_include_three_summary_prompt_phases(self) -> None:
        context = SummaryContext(
            base="main",
            branch="feat/x",
            commits="abc change",
            stat="file.py | 1 +",
            ignores=[],
            groups=[],
        )
        group = SummaryGroup("src", ["src/file.py"], "diff --git", False)

        self.assertIn("Return plain text notes only", build_group_prompt(context, group))
        self.assertIn("Important changes:", build_group_prompt(context, group))
        self.assertIn(
            "Return this exact plain-text shape",
            build_final_prompt(context, ["### src"]),
        )
        self.assertIn(
            "Grouped summaries from the earlier summary step:",
            build_final_prompt(context, ["### src"]),
        )
        self.assertNotIn("PR branch:", build_final_prompt(context, ["### src"]))

    def test_parse_summary_result_requires_title_and_body(self) -> None:
        result = parse_summary_result("TITLE: feat: add thing\n\nBODY:\n## Summary\n- done")

        self.assertEqual(result["title"], "feat: add thing")
        self.assertEqual(result["body"], "## Summary\n- done")

    def test_parse_summary_result_rejects_bad_prefix(self) -> None:
        with self.assertRaises(ValueError):
            parse_summary_result("TITLE: nope\n\nBODY:\n## Summary\n- done")

    def test_parse_summary_result_can_skip_title(self) -> None:
        result = parse_summary_result(
            "BODY:\n## Summary\n- done",
            TitleConfig(update=False, enforce_prefix=True, prefixes=["feat:"]),
        )

        self.assertEqual(result, {"body": "## Summary\n- done"})

    def test_parse_summary_result_can_allow_any_title_format(self) -> None:
        result = parse_summary_result(
            "TITLE: Ship thing\n\nBODY:\n## Summary\n- done",
            TitleConfig(update=True, enforce_prefix=False, prefixes=["feat:"]),
        )

        self.assertEqual(result["title"], "Ship thing")

    def test_parse_summary_result_cleans_body_spacing(self) -> None:
        result = parse_summary_result(
            "TITLE: feat: add thing\n\n"
            "BODY:\n"
            "## Summary\n"
            "- added thing\n\n\n"
            "## Risk\n"
            "- small migration risk\n"
        )

        self.assertEqual(result["title"], "feat: add thing")
        self.assertEqual(
            result["body"],
            "## Summary\n- added thing\n\n## Risk\n- small migration risk",
        )

    def test_clean_summary_body_collapses_blank_lines(self) -> None:
        body = clean_summary_body("## Summary\n- done\n\n\n## Validation\n- uv run tests")

        self.assertEqual(body, "## Summary\n- done\n\n## Validation\n- uv run tests")

    def test_group_summary_text_wraps_area_notes(self) -> None:
        text = group_summary_text("- changed code", "src")

        self.assertEqual(text, "### src\n\n- changed code")

    def test_parse_name_status_uses_destination_for_renames(self) -> None:
        files = parse_name_status("M\tsrc/a.py\nR100\told.py\tnew.py")

        self.assertEqual(files, [("M", "src/a.py"), ("R100", "new.py")])

    def test_split_groups_keeps_small_changes_together(self) -> None:
        groups = split_groups([("M", "src/a.py"), ("M", "tests/test_a.py")], max_groups=15)

        self.assertEqual(groups, [("src", ["src/a.py"]), ("tests", ["tests/test_a.py"])])

    def test_shared_context_messages_are_action_agnostic(self) -> None:
        context = SummaryContext(
            base="main",
            branch="feat/x",
            commits="abc change",
            stat="file.py | 1 +",
            name_status="M\tsrc/a.py\nM\ttests/test_a.py",
            ignores=[],
            groups=[SummaryGroup("all changes", ["src/a.py"], "diff", False)],
        )

        self.assertEqual(
            context_ready_message(context, "review"),
            "📦 Context ready: 2 files, 1 review group",
        )
        self.assertEqual(
            single_group_message("summary"),
            "➡️  Single summary group — skipping parallel workers",
        )

    def test_collect_summary_context_uses_ignores_and_trims_group_diff(self) -> None:
        config = SummaryConfig(
            model="gemma4:e4b",
            api_base="http://localhost:11434",
            num_ctx=8192,
            max_group_chars=10,
            max_groups=15,
            summary_tokens=900,
            final_tokens=1800,
            temperature=0.1,
            workers=5,
            timeout=420,
            ignores=["dist/**"],
            title=TitleConfig(update=True, enforce_prefix=True, prefixes=["feat:"]),
            split_group_prompt="",
            final_prompt="",
            split_group_extra_instructions="",
            final_extra_instructions="",
        )
        commands = []

        def fake_run(cmd: list[str], cwd: Path, check: bool = True) -> str:
            commands.append(cmd)
            joined = " ".join(cmd)
            if "defaultBranchRef" in joined:
                return "main"
            if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return "feat/x"
            if cmd[:2] == ["git", "merge-base"]:
                return "base-sha"
            if "--name-status" in cmd:
                return "M\tsrc/a.py"
            if "--stat" in cmd:
                return "src/a.py | 1 +"
            if cmd[:2] == ["git", "log"]:
                return "abc change"
            if cmd[:2] == ["git", "diff"]:
                return "01234567890abcdef"
            raise AssertionError(cmd)

        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch("shippy.summary.engine.run", fake_run),
        ):
            context = collect_summary_context(Path("."), config)

        self.assertEqual(context.base, "main")
        self.assertEqual(context.branch, "feat/x")
        self.assertEqual(context.groups[0].diff, "0123456789\n\n[group diff truncated]\n")
        self.assertTrue(any(":(exclude)dist/**" in cmd for cmd in commands))

    def test_collect_summary_context_keeps_small_pr_in_one_group(self) -> None:
        config = SummaryConfig(
            model="gemma4:e4b",
            api_base="http://localhost:11434",
            num_ctx=8192,
            max_group_chars=100,
            max_groups=15,
            summary_tokens=900,
            final_tokens=1800,
            temperature=0.1,
            workers=5,
            timeout=420,
            ignores=[],
            title=TitleConfig(update=True, enforce_prefix=True, prefixes=["feat:"]),
            split_group_prompt="",
            final_prompt="",
            split_group_extra_instructions="",
            final_extra_instructions="",
        )

        def fake_run(cmd: list[str], cwd: Path, check: bool = True) -> str:
            joined = " ".join(cmd)
            if "defaultBranchRef" in joined:
                return "main"
            if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return "feat/x"
            if cmd[:2] == ["git", "merge-base"]:
                return "base-sha"
            if "--name-status" in cmd:
                return "M\tsrc/a.py\nM\ttests/test_a.py"
            if "--stat" in cmd:
                return "src/a.py | 1 +"
            if cmd[:2] == ["git", "log"]:
                return "abc change"
            if cmd[:2] == ["git", "diff"]:
                return "small diff"
            raise AssertionError(cmd)

        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch("shippy.summary.engine.run", fake_run),
        ):
            context = collect_summary_context(Path("."), config)

        self.assertEqual(len(context.groups), 1)
        self.assertEqual(context.groups[0].name, "all changes")
        self.assertEqual(context.groups[0].diff, "small diff")


if __name__ == "__main__":
    unittest.main()
