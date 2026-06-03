"""Git context collection for PR review prompts."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from shippy.errors import CommandError


@dataclass(frozen=True)
class PullRequestContext:
    base: str
    branch: str
    commits: str
    stat: str
    name_status: str
    diff: str
    trimmed: bool


def run(cmd: list[str], cwd: Path, check: bool = True) -> str:
    if not cmd:
        raise CommandError("empty command")
    if not cwd.exists():
        raise CommandError(f"missing working directory: {cwd}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        command = " ".join(cmd)
        message = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise CommandError(f"{command}: {message}")
    return result.stdout.strip()


def current_branch(repo_root: Path) -> str:
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    if branch == "HEAD":
        raise CommandError("git repository is in detached HEAD state")
    if not branch:
        raise CommandError("could not determine current branch")
    return branch


def default_branch(repo_root: Path) -> str:
    try:
        return run(
            [
                "gh",
                "repo",
                "view",
                "--json",
                "defaultBranchRef",
                "--jq",
                ".defaultBranchRef.name",
            ],
            repo_root,
        )
    except CommandError:
        return "main"


def discover_repo_root(cwd: Path) -> Path:
    """Return the Git top-level directory for any path inside a work tree."""
    if not cwd.exists():
        raise CommandError(f"working directory does not exist: {cwd}")
    root = run(["git", "rev-parse", "--show-toplevel"], cwd)
    if not root:
        raise CommandError(f"could not determine git repository root from: {cwd}")
    return Path(root).resolve()


def collect_pr_context(
    repo_root: Path,
    max_chars: int,
    ignores: list[str],
) -> PullRequestContext:
    if max_chars < 1:
        raise CommandError("max_chars must be greater than 0")
    validate_repo_root(repo_root)
    base = default_branch(repo_root)
    branch = current_branch(repo_root)
    merge_base = run(["git", "merge-base", f"origin/{base}", "HEAD"], repo_root)
    excludes = [f":(exclude){pattern}" for pattern in ignores]
    pathspec = [".", *excludes]
    commit_range = f"{merge_base}..HEAD"

    commits = run(
        ["git", "log", "--oneline", "--decorate=no", commit_range],
        repo_root,
    )
    stat = run(["git", "diff", "--stat", commit_range, "--", *pathspec], repo_root)
    name_status = run(
        ["git", "diff", "--name-status", commit_range, "--", *pathspec],
        repo_root,
    )
    diff = run(
        ["git", "diff", "--unified=30", commit_range, "--", *pathspec],
        repo_root,
    )
    trimmed = len(diff) > max_chars
    if trimmed:
        diff = diff[:max_chars] + "\n\n[diff truncated]\n"

    return PullRequestContext(
        base=base,
        branch=branch,
        commits=commits,
        stat=stat,
        name_status=name_status,
        diff=diff,
        trimmed=trimmed,
    )


def validate_repo_root(repo_root: Path) -> None:
    if not repo_root.exists():
        raise CommandError(f"repo root does not exist: {repo_root}")
    inside = run(["git", "rev-parse", "--is-inside-work-tree"], repo_root)
    if inside != "true":
        raise CommandError(f"not a git work tree: {repo_root}")
