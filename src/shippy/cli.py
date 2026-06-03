"""Command line entrypoint for local PR summary and review."""

from __future__ import annotations

import argparse
import sys
from importlib import resources
from pathlib import Path

from shippy import __version__
from shippy.config import load_review_config, load_summary_config
from shippy.constants import (
    CLI_DESCRIPTION,
    CLI_PROG,
    COMMAND_INIT,
    COMMAND_REVIEW,
    COMMAND_SUMMARY,
)
from shippy.errors import ShippyError
from shippy.git import discover_repo_root
from shippy.github import GitHubClient
from shippy.review import review_pull_request
from shippy.summary import summarize_pull_request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=CLI_PROG,
        description=CLI_DESCRIPTION,
    )
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--pr-url")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("command", choices=[COMMAND_INIT, COMMAND_SUMMARY, COMMAND_REVIEW])
    return parser


def init_config(repo_root: Path, config_path: Path | None = None) -> Path:
    target = config_path or repo_root / ".shippy.toml"
    if target.exists():
        raise ShippyError(f"config already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    template = resources.files("shippy.templates").joinpath(".shippy.toml")
    target.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def main() -> int:
    args = build_parser().parse_args()
    try:
        repo_root = (
            Path(args.repo_root).resolve() if args.repo_root else discover_repo_root(Path.cwd())
        )
        if args.command == COMMAND_INIT:
            path = init_config(repo_root, args.config)
            print(f"created {path}")
            return 0
        if args.command == COMMAND_SUMMARY:
            config = load_summary_config(repo_root, args.config)
            summarize_pull_request(repo_root, args.pr_url, config)
        if args.command == COMMAND_REVIEW:
            config = load_review_config(repo_root, args.config)
            pr_url = args.pr_url or GitHubClient(repo_root).current_branch_pull_request_url()
            review_pull_request(repo_root, pr_url, config)
        return 0
    except (ShippyError, ValueError) as error:
        print(f"shippy: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
