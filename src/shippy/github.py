"""GitHub CLI adapter for sticky PR review comments."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from shippy.git import run
from shippy.review.constants import COMMENT_MARKER


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    body: str
    url: str


@dataclass(frozen=True)
class GitHubContext:
    repo: str
    user: str
    pr_number: int


class GitHubClient:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def pull_request(self, pr_url: str) -> PullRequest:
        raw = run(
            ["gh", "pr", "view", pr_url, "--json", "number,title,body,url"],
            self.repo_root,
        )
        data = json.loads(raw)
        return PullRequest(
            number=data["number"],
            title=data.get("title") or "",
            body=data.get("body") or "",
            url=data.get("url") or pr_url,
        )

    def current_branch_pull_request_url(self) -> str:
        raw = run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                run(["git", "rev-parse", "--abbrev-ref", "HEAD"], self.repo_root),
                "--state",
                "open",
                "--json",
                "number,title,url",
            ],
            self.repo_root,
        )
        prs = json.loads(raw)
        if not isinstance(prs, list) or not prs:
            branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], self.repo_root)
            raise ValueError(f"no open PR found for current branch: {branch}")
        return str(prs[0]["url"])

    def context(self, pr_number: int) -> GitHubContext:
        repo = run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
            self.repo_root,
        )
        user = run(["gh", "api", "user", "--jq", ".login"], self.repo_root)
        return GitHubContext(repo=repo, user=user, pr_number=pr_number)

    def find_sticky_comment(self, context: GitHubContext) -> str:
        comments = run(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/{context.repo}/issues/{context.pr_number}/comments",
                "--jq",
                ".[] | @json",
            ],
            self.repo_root,
        )
        for line in comments.splitlines():
            if not line.strip():
                continue
            comment = json.loads(line)
            body = comment.get("body") or ""
            login = comment.get("user", {}).get("login")
            if login == context.user and COMMENT_MARKER in body:
                return str(comment["id"])
        return ""

    def upsert_comment(
        self,
        context: GitHubContext,
        body: str,
        comment_id: str = "",
    ) -> str:
        body_file = _write_temp(body)
        try:
            if comment_id:
                return self._patch_comment(context, comment_id, body_file)
            return self._create_comment(context, body_file)
        finally:
            Path(body_file).unlink(missing_ok=True)

    def _patch_comment(
        self,
        context: GitHubContext,
        comment_id: str,
        body_file: str,
    ) -> str:
        run(
            [
                "gh",
                "api",
                "--method",
                "PATCH",
                f"repos/{context.repo}/issues/comments/{comment_id}",
                "--field",
                f"body=@{body_file}",
                "--jq",
                ".id",
            ],
            self.repo_root,
        )
        return comment_id

    def _create_comment(self, context: GitHubContext, body_file: str) -> str:
        return run(
            [
                "gh",
                "api",
                "--method",
                "POST",
                f"repos/{context.repo}/issues/{context.pr_number}/comments",
                "--field",
                f"body=@{body_file}",
                "--jq",
                ".id",
            ],
            self.repo_root,
        )


def _write_temp(text: str) -> str:
    with tempfile.NamedTemporaryFile("w", delete=False) as file:
        file.write(text)
        return file.name
