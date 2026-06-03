"""Markdown PR review generation and publishing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from shippy.github import GitHubClient, PullRequest
from shippy.ollama import OllamaClient, OllamaOptions
from shippy.review.constants import (
    AI_REVIEW_HEADING,
    COMMENT_MARKER,
    DEFAULT_REVIEW_FINAL_PROMPT_TEMPLATE,
    DEFAULT_REVIEW_GROUP_PROMPT_TEMPLATE,
    NO_BLOCKING_ISSUES,
    NO_VALIDATION_VISIBLE,
    REVIEW_FAILURE_BODY_TEMPLATE,
    REVIEW_PENDING_BODY,
    UNKNOWN_FAILURE,
)
from shippy.workflow import (
    WorkContext,
    WorkGroup,
    collect_work_context,
    context_ready_message,
    render_configured_prompt,
    run_workers,
    single_group_message,
    work_group_values,
)

if TYPE_CHECKING:
    from shippy.config import ReviewConfig


@dataclass(frozen=True)
class ReviewGroup(WorkGroup):
    pass


@dataclass(frozen=True)
class ReviewContext(WorkContext):
    groups: Sequence[ReviewGroup]


def say(message: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} {message}", flush=True)


def review_pull_request(
    repo_root: Path,
    pr_url: str,
    config: ReviewConfig,
) -> None:
    github = GitHubClient(repo_root)
    ollama = OllamaClient(config.api_base, config.model)
    ollama.assert_model_available()

    pr = github.pull_request(pr_url)
    context = github.context(pr.number)
    comment_id = github.find_sticky_comment(context)
    comment_id = github.upsert_comment(context, pending_body(), comment_id)

    try:
        say("🧭 Collecting PR review context...")
        review_context = collect_review_context(repo_root, config)
        say(context_ready_message(review_context, "review"))
        area_reviews = review_groups(ollama, review_context, pr, config)
        say(f"📝 Asking {config.model} for final markdown review...")
        result = ollama.generate_with_stats(
            prompt=build_review_prompt(
                review_context,
                pr,
                prompt_template=config.final_prompt,
                extra_instructions=config.final_extra_instructions,
                area_reviews="\n\n".join(area_reviews),
            ),
            options=OllamaOptions(
                num_ctx=config.num_ctx,
                num_predict=config.num_predict,
                temperature=config.temperature,
                timeout=config.timeout,
            ),
        )
        usage = result.usage_text()
        if usage:
            say(f"📊 Final review tokens: {usage}")
        github.upsert_comment(context, normalize_review(result.text), comment_id)
    except Exception as error:
        body = failure_body(f"{type(error).__name__}: {error}")
        github.upsert_comment(context, body, comment_id)
        return

    say("✅ Updated PR review comment")


def collect_review_context(repo_root: Path, config: ReviewConfig) -> ReviewContext:
    context = collect_work_context(
        repo_root,
        max_group_chars=config.max_group_chars,
        max_groups=config.max_groups,
        ignores=config.ignores,
        unified=30,
        truncation_marker="[review group diff truncated]",
    )
    groups = [
        ReviewGroup(group.name, group.paths, group.diff, group.trimmed) for group in context.groups
    ]
    return ReviewContext(
        base=context.base,
        branch=context.branch,
        commits=context.commits,
        stat=context.stat,
        name_status=context.name_status,
        ignores=context.ignores,
        groups=groups,
    )


def review_groups(
    ollama: OllamaClient,
    context: ReviewContext,
    pr: PullRequest,
    config: ReviewConfig,
) -> list[str]:
    if len(context.groups) == 1:
        say(single_group_message("review"))
        return []

    say(f"🧩 Reviewing {len(context.groups)} groups with {config.workers} workers...")

    def review(group: ReviewGroup) -> str:
        result = ollama.generate_with_stats(
            build_review_group_prompt(
                context,
                group,
                pr,
                config.split_group_prompt,
                config.split_group_extra_instructions,
            ),
            OllamaOptions(
                num_ctx=config.num_ctx,
                num_predict=config.group_tokens,
                temperature=config.temperature,
                timeout=config.timeout,
            ),
        )
        usage = result.usage_text()
        if usage:
            say(f"📊 Review group {group.name}: {usage}")
        return result.text.strip()

    reviews = run_workers(context.groups, config.workers, review)
    reviews.sort()
    return reviews


def build_review_group_prompt(
    context: ReviewContext,
    group: ReviewGroup,
    pr: PullRequest,
    prompt_template: str = "",
    extra_instructions: str = "",
) -> str:
    trim_note = (
        "Some diff context was truncated; review only visible context."
        if group.trimmed
        else "Use the available diff context."
    )
    values = work_group_values(context, group)
    values.update(
        {
            "area": group.name,
            "no_blocking_issues": NO_BLOCKING_ISSUES,
            "no_validation_visible": NO_VALIDATION_VISIBLE,
            "trim_note": trim_note,
            "pr_title": pr.title,
            "pr_url": pr.url,
            "pr_body": pr.body,
            "commits": context.commits,
            "stat": context.stat,
        },
    )
    return render_configured_prompt(
        default_template=DEFAULT_REVIEW_GROUP_PROMPT_TEMPLATE,
        prompt_template=prompt_template,
        values=values,
        extra_instructions=extra_instructions,
    )


def build_review_prompt(
    context: ReviewContext,
    pr: PullRequest,
    prompt_template: str = "",
    extra_instructions: str = "",
    area_reviews: str = "",
) -> str:
    groups = getattr(context, "groups", [])
    trim_note = (
        "Some diff context was truncated; review only visible context."
        if (groups and any(group.trimmed for group in groups))
        or (not groups and getattr(context, "trimmed", False))
        else "Use the available review notes and diff context."
    )
    diff = "\n\n".join(group.diff for group in groups) if groups else getattr(context, "diff", "")
    values = {
        "pr_title": pr.title,
        "pr_url": pr.url,
        "pr_body": pr.body,
        "branch": context.branch,
        "base": context.base,
        "commits": context.commits,
        "stat": context.stat,
        "changed_files": context.name_status,
        "diff": diff,
        "area_reviews": area_reviews,
        "trim_note": trim_note,
    }
    return render_configured_prompt(
        default_template=DEFAULT_REVIEW_FINAL_PROMPT_TEMPLATE,
        prompt_template=prompt_template,
        values=values,
        extra_instructions=extra_instructions,
    )


def normalize_review(markdown: str) -> str:
    text = markdown.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not text.startswith(AI_REVIEW_HEADING):
        text = f"{AI_REVIEW_HEADING}\n\n" + text
    return f"{COMMENT_MARKER}\n{text}\n"


def pending_body() -> str:
    return REVIEW_PENDING_BODY


def failure_body(reason: str) -> str:
    return REVIEW_FAILURE_BODY_TEMPLATE.format(reason=reason.strip() or UNKNOWN_FAILURE)
