"""Shared grouped PR context and worker helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import TypeVar

from shippy.errors import CommandError
from shippy.git import run
from shippy.prompts import append_extra_instructions, render_prompt


@dataclass(frozen=True)
class WorkGroup:
    name: str
    paths: Sequence[str]
    diff: str
    trimmed: bool


@dataclass(frozen=True)
class WorkContext:
    base: str
    branch: str
    commits: str
    stat: str
    ignores: list[str]
    groups: Sequence[WorkGroup]
    name_status: str = ""


T = TypeVar("T")


def collect_work_context(
    repo_root: Path,
    *,
    max_group_chars: int,
    max_groups: int,
    ignores: list[str],
    unified: int,
    truncation_marker: str,
    runner: Callable[[list[str], Path, bool], str] = run,
) -> WorkContext:
    if max_group_chars < 1:
        raise CommandError("max_group_chars must be greater than 0")
    base = (
        runner(
            ["gh", "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"],
            repo_root,
            check=False,
        )
        or "main"
    )
    branch = runner(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root, True)
    if branch == "HEAD":
        raise CommandError("git repository is in detached HEAD state")
    if not branch:
        raise CommandError("could not determine current branch")
    merge_base = runner(["git", "merge-base", f"origin/{base}", "HEAD"], repo_root, True)
    excludes = [f":(exclude){pattern}" for pattern in ignores]
    pathspec = [".", *excludes]
    commit_range = f"{merge_base}..HEAD"

    commits = runner(["git", "log", "--oneline", "--decorate=no", commit_range], repo_root, True)
    stat = runner(["git", "diff", "--stat", commit_range, "--", *pathspec], repo_root, True)
    name_status = runner(
        ["git", "diff", "--name-status", commit_range, "--", *pathspec], repo_root, True
    )
    full_diff = runner(
        ["git", "diff", f"--unified={unified}", commit_range, "--", *pathspec],
        repo_root,
        True,
    )
    if len(full_diff) <= max_group_chars:
        return WorkContext(
            base=base,
            branch=branch,
            commits=commits,
            stat=stat,
            name_status=name_status,
            ignores=ignores,
            groups=[
                WorkGroup(
                    name="all changes",
                    paths=[path for _, path in parse_name_status(name_status)],
                    diff=full_diff,
                    trimmed=False,
                )
            ],
        )

    groups = []
    for name, paths in split_groups(parse_name_status(name_status), max_groups):
        diff_paths = paths or pathspec
        diff = runner(
            ["git", "diff", f"--unified={unified}", commit_range, "--", *diff_paths],
            repo_root,
            True,
        )
        trimmed = len(diff) > max_group_chars
        if trimmed:
            suffix = f"\n\n{truncation_marker}\n" if truncation_marker else ""
            diff = diff[:max_group_chars] + suffix
        groups.append(WorkGroup(name=name, paths=paths, diff=diff, trimmed=trimmed))

    return WorkContext(
        base=base,
        branch=branch,
        commits=commits,
        stat=stat,
        name_status=name_status,
        ignores=ignores,
        groups=groups,
    )


def parse_name_status(output: str) -> list[tuple[str, str]]:
    files = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            files.append((parts[0], parts[-1]))
    return files


def split_groups(files: list[tuple[str, str]], max_groups: int) -> list[tuple[str, list[str]]]:
    if max_groups < 1:
        raise ValueError("max_groups must be greater than 0")
    if not files:
        return [("root", [])]
    max_files = max(20, ceil(len(files) / max_groups))
    top_counts: dict[str, int] = {}
    for _, path in files:
        top = path.split("/", 1)[0] if "/" in path else "root"
        top_counts[top] = top_counts.get(top, 0) + 1

    groups: dict[str, list[str]] = {}
    for _, path in files:
        parts = path.split("/")
        if len(parts) == 1:
            name = "root"
        elif top_counts[parts[0]] > max_files and len(parts) > 2:
            name = "/".join(parts[:2])
        else:
            name = parts[0]
        groups.setdefault(name, []).append(path)

    split = []
    for name, paths in sorted(groups.items()):
        paths = sorted(paths)
        if len(paths) <= max_files:
            split.append((name, paths))
            continue
        for index in range(0, len(paths), max_files):
            split.append((f"{name} #{index // max_files + 1}", paths[index : index + max_files]))

    if len(split) <= max_groups:
        return split
    split.sort(key=lambda item: len(item[1]), reverse=True)
    keep = split[: max_groups - 1]
    rest = [path for _, paths in split[max_groups - 1 :] for path in paths]
    keep.append(("mixed-small-changes", sorted(rest)))
    return sorted(keep)


def run_workers(items: Sequence[WorkGroup], workers: int, job: Callable[[WorkGroup], T]) -> list[T]:
    if workers < 1:
        raise ValueError("workers must be greater than 0")
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(job, item): item for item in items}
        for future in as_completed(futures):
            results.append(future.result())
    return results


def bullet_list(values: Sequence[str]) -> str:
    return "\n".join(f"- {value}" for value in values)


def work_group_values(context: WorkContext, group: WorkGroup) -> dict[str, str]:
    return {
        "area": group.name,
        "branch": context.branch,
        "base": context.base,
        "ignored_paths": bullet_list(context.ignores),
        "files": bullet_list(group.paths),
        "diff": group.diff,
    }


def render_configured_prompt(
    *,
    default_template: str,
    prompt_template: str,
    values: dict[str, str],
    extra_instructions: str = "",
) -> str:
    template = prompt_template if prompt_template.strip() else default_template
    return append_extra_instructions(render_prompt(template, values), extra_instructions)
