"""Markdown PR review generation and publishing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from shippy.github import GitHubClient, GitHubContext, PullRequest
from shippy.log import SessionLogger
from shippy.ollama import GenerateResult, OllamaClient, OllamaOptions
from shippy.review.constants import (
    AI_REVIEW_HEADING,
    COMMENT_MARKER,
    CONTEXT_ESCAPE_PHRASES,
    DEFAULT_REVIEW_FINAL_PROMPT_TEMPLATE,
    DEFAULT_REVIEW_GROUP_PROMPT_TEMPLATE,
    NO_BLOCKING_ISSUES,
    NO_REVIEW_TEXT,
    NO_VALIDATION_VISIBLE,
    REVIEW_FAILURE_BODY_TEMPLATE,
    REVIEW_PENDING_BODY,
    REVIEW_RESULT_PREFIXES,
    REVIEW_VERDICT_HEADING,
    UNKNOWN_FAILURE,
    UNSTRUCTURED_REVIEW_TEMPLATE,
)
from shippy.workflow import (
    WorkContext,
    WorkGroup,
    collect_work_context,
    context_ready_message,
    render_configured_prompt,
    run_workers,
    single_group_message,
    truncation_messages,
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
    logger = SessionLogger(repo_root, "review", config.debug.log_dir, config.debug.verbose)
    ollama.assert_model_available()

    pr = github.pull_request(pr_url)
    context = github.context(pr.number)
    comment_id = github.find_sticky_comment(context)
    comment_id = github.upsert_comment(context, pending_body(), comment_id)

    try:
        review = generate_review(repo_root, ollama, pr, config, logger)
    except Exception as error:
        handle_review_error(github, context, comment_id, logger, error)
        raise

    github.upsert_comment(context, normalize_review(review), comment_id)
    say("✅ Updated PR review comment")


def generate_review(
    repo_root: Path,
    ollama: OllamaClient,
    pr: PullRequest,
    config: ReviewConfig,
    logger: SessionLogger,
) -> str:
    review_context = prepare_review_context(repo_root, pr, config, logger)
    area_reviews = review_groups(ollama, review_context, pr, config, logger)
    result = final_review(ollama, review_context, pr, area_reviews, config, logger)
    return result.text


def prepare_review_context(
    repo_root: Path,
    pr: PullRequest,
    config: ReviewConfig,
    logger: SessionLogger,
) -> ReviewContext:
    say("🧭 Collecting PR review context...")
    context = collect_review_context(repo_root, config)
    say(context_ready_message(context, "review"))
    for message in truncation_messages(context):
        say(message)
    logger.log(
        "review_context",
        pr_url=pr.url,
        pr_title=pr.title,
        branch=context.branch,
        base=context.base,
        groups=[group_log(group) for group in context.groups],
    )
    return context


def final_review(
    ollama: OllamaClient,
    context: ReviewContext,
    pr: PullRequest,
    area_reviews: list[str],
    config: ReviewConfig,
    logger: SessionLogger,
) -> GenerateResult:
    say(f"📝 Asking {config.model} for final markdown review...")
    prompt = build_review_prompt(
        context,
        pr,
        prompt_template=config.final_prompt,
        extra_instructions=config.final_extra_instructions,
        area_reviews="\n\n".join(area_reviews),
    )
    options = OllamaOptions(
        num_ctx=config.num_ctx,
        num_predict=config.num_predict,
        temperature=config.temperature,
        timeout=config.timeout,
    )
    logger.request("review_final_request", prompt, model=config.model, options=options)
    result = ollama.generate_with_stats(prompt=prompt, options=options)
    logger.response(
        "review_final_response",
        result.text,
        prompt_tokens=result.prompt_tokens,
        output_tokens=result.output_tokens,
        attempts=retry_count(result),
    )
    usage = result.usage_text()
    if usage:
        say(f"✅ Finished final review: {usage}{attempt_text(result)}")
    return result


def handle_review_error(
    github: GitHubClient,
    context: GitHubContext,
    comment_id: str,
    logger: SessionLogger,
    error: Exception,
) -> None:
    message = f"{type(error).__name__}: {error}"
    logger.log("review_error", error=message)
    say(f"❌ Review failed: {message}")
    github.upsert_comment(context, failure_body(message), comment_id)


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
        ReviewGroup(group.name, group.paths, group.diff, group.trimmed, group.truncations)
        for group in context.groups
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
    logger: SessionLogger | None = None,
) -> list[str]:
    if len(context.groups) == 1:
        say(single_group_message("review"))
        return []

    say(f"🧩 Reviewing {len(context.groups)} groups with {config.workers} parallel workers...")

    def review(group: ReviewGroup) -> str:
        prompt = build_review_group_prompt(
            context,
            group,
            pr,
            config.split_group_prompt,
            config.split_group_extra_instructions,
        )
        options = OllamaOptions(
            num_ctx=config.num_ctx,
            num_predict=config.group_tokens,
            temperature=config.temperature,
            timeout=config.timeout,
        )
        if logger:
            logger.request(
                "review_group_request",
                prompt,
                group=group_log(group),
                options=options,
            )
        try:
            result = ollama.generate_with_stats(prompt, options)
        except Exception as error:
            if logger:
                logger.log(
                    "review_group_error",
                    group=group.name,
                    error=f"{type(error).__name__}: {error}",
                )
            raise
        if logger:
            logger.response(
                "review_group_response",
                result.text,
                group=group.name,
                prompt_tokens=result.prompt_tokens,
                output_tokens=result.output_tokens,
                attempts=retry_count(result),
            )
        usage = result.usage_text()
        if usage:
            say(f"✅ Finished review group {group.name}: {usage}{attempt_text(result)}")
        return result.text.strip()

    reviews = run_workers(context.groups, config.workers, review)
    reviews.sort()
    return reviews


def group_log(group: ReviewGroup | WorkGroup) -> dict[str, object]:
    return {
        "name": group.name,
        "paths": group.paths,
        "trimmed": group.trimmed,
        "diff_chars": len(group.diff),
        "truncations": group.truncations,
    }


def retry_count(result: GenerateResult) -> int | None:
    return result.attempts if result.attempts > 1 else None


def attempt_text(result: GenerateResult) -> str:
    return f", attempts {result.attempts}" if result.attempts > 1 else ""


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
    review_context = area_reviews.strip() or diff
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
        "review_context": review_context,
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
    text = repair_review_shape(text)
    if not text.startswith(AI_REVIEW_HEADING):
        text = f"{AI_REVIEW_HEADING}\n\n" + text
    return f"{COMMENT_MARKER}\n{text}\n"


def repair_review_shape(markdown: str) -> str:
    text = strip_context_requests(markdown.strip())
    if is_structured_review(text):
        return text
    return UNSTRUCTURED_REVIEW_TEMPLATE.format(review_text=text or NO_REVIEW_TEXT).strip()


def is_structured_review(markdown: str) -> bool:
    lowered = markdown.lower()
    has_verdict = REVIEW_VERDICT_HEADING.lower() in lowered
    has_result = any(prefix.lower() in lowered for prefix in REVIEW_RESULT_PREFIXES)
    return has_verdict and has_result


def strip_context_requests(markdown: str) -> str:
    lines = [
        line
        for line in markdown.splitlines()
        if not any(phrase in line.lower() for phrase in CONTEXT_ESCAPE_PHRASES)
    ]
    return "\n".join(lines).strip()


def pending_body() -> str:
    return REVIEW_PENDING_BODY


def failure_body(reason: str) -> str:
    return REVIEW_FAILURE_BODY_TEMPLATE.format(reason=reason.strip() or UNKNOWN_FAILURE)
