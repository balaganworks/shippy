import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from shippy.errors import CommandError
from shippy.git import (
    collect_pr_context,
    current_branch,
    discover_repo_root,
    run,
    validate_repo_root,
)


class GitTest(unittest.TestCase):
    def test_run_rejects_empty_command(self) -> None:
        with self.assertRaises(CommandError):
            run([], Path("."))

    def test_run_rejects_missing_cwd(self) -> None:
        with self.assertRaises(CommandError):
            run(["git", "status"], Path("/path/that/does/not/exist"))

    def test_run_raises_command_error_with_stderr(self) -> None:
        result = subprocess.CompletedProcess(["git"], 1, stdout="", stderr="bad")

        with (
            patch("subprocess.run", return_value=result),
            self.assertRaisesRegex(CommandError, "bad"),
        ):
            run(["git"], Path("."))

    def test_run_allows_failed_command_when_check_false(self) -> None:
        result = subprocess.CompletedProcess(["git"], 1, stdout="fallback", stderr="bad")

        with patch("subprocess.run", return_value=result):
            self.assertEqual(run(["git"], Path("."), check=False), "fallback")

    def test_current_branch_rejects_detached_head(self) -> None:
        with patch("shippy.git.run", return_value="HEAD"), self.assertRaises(CommandError):
            current_branch(Path("."))

    def test_validate_repo_root_requires_git_work_tree(self) -> None:
        with patch("shippy.git.run", return_value="false"), self.assertRaises(CommandError):
            validate_repo_root(Path("."))

    def test_discover_repo_root_uses_git_top_level(self) -> None:
        with patch("shippy.git.run", return_value="/repo/root") as mocked_run:
            root = discover_repo_root(Path("."))

        self.assertEqual(root, Path("/repo/root"))
        mocked_run.assert_called_once_with(["git", "rev-parse", "--show-toplevel"], Path("."))

    def test_collect_pr_context_rejects_invalid_max_chars(self) -> None:
        with self.assertRaises(CommandError):
            collect_pr_context(Path("."), max_chars=0, ignores=[])

    def test_collect_pr_context_uses_pathspec_and_trims_diff(self) -> None:
        commands = []

        def fake_run(cmd: list[str], cwd: Path, check: bool = True) -> str:
            commands.append(cmd)
            joined = " ".join(cmd)
            if cmd[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
                return "true"
            if "defaultBranchRef" in joined:
                return "main"
            if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return "feat/x"
            if cmd[:2] == ["git", "merge-base"]:
                return "base-sha"
            if cmd[:2] == ["git", "log"]:
                return "abc change"
            if "--stat" in cmd:
                return "src/a.py | 1 +"
            if "--name-status" in cmd:
                return "M\tsrc/a.py"
            if cmd[:2] == ["git", "diff"]:
                return "01234567890"
            raise AssertionError(cmd)

        with patch("shippy.git.run", fake_run):
            context = collect_pr_context(Path("."), max_chars=5, ignores=["dist/**"])

        self.assertEqual(context.base, "main")
        self.assertEqual(context.branch, "feat/x")
        self.assertEqual(context.diff, "01234\n\n[diff truncated]\n")
        self.assertTrue(context.trimmed)
        self.assertTrue(any(":(exclude)dist/**" in cmd for cmd in commands))


if __name__ == "__main__":
    unittest.main()
