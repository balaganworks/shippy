"""PR title and body generation."""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from shippy.git import run
from shippy.github import GitHubClient
from shippy.log import SessionLogger
from shippy.ollama import GenerateResult, OllamaClient, OllamaOptions
from shippy.review.engine import say
from shippy.summary.constants import (
    DEFAULT_FINAL_PROMPT_TEMPLATE,
    DEFAULT_GROUP_PROMPT_TEMPLATE,
    DEFAULT_TITLE_PREFIXES,
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
    from shippy.config import SummaryConfig, TitleConfig


@dataclass(frozen=True)
class SummaryGroup(WorkGroup):
    pass


@dataclass(frozen=True)
class SummaryContext(WorkContext):
    groups: Sequence[SummaryGroup]


def summarize_pull_request(repo_root: Path, pr_url: str | None, config: SummaryConfig) -> None:
    github = GitHubClient(repo_root)
    ollama = OllamaClient(config.api_base, config.model)
    logger = SessionLogger(repo_root, "summary", config.debug.log_dir, config.debug.verbose)
    ollama.assert_model_available()

    try:
        result = generate_summary(repo_root, ollama, config, logger)
        publish_summary(repo_root, github, pr_url, result)
    except Exception as error:
        handle_summary_error(logger, error)
        raise

    say("✅ Updated PR title/body")


def generate_summary(
    repo_root: Path,
    ollama: OllamaClient,
    config: SummaryConfig,
    logger: SessionLogger,
) -> dict[str, str]:
    context = prepare_summary_context(repo_root, config, logger)
    summaries = summarize_groups(ollama, context, config, logger)
    final = final_summary(ollama, context, summaries, config, logger)
    return parse_summary_result(final.text, config.title)


def prepare_summary_context(
    repo_root: Path,
    config: SummaryConfig,
    logger: SessionLogger,
) -> SummaryContext:
    say("🧭 Collecting PR summary context...")
    context = collect_summary_context(repo_root, config)
    logger.log(
        "summary_context",
        branch=context.branch,
        base=context.base,
        groups=[group_log(group) for group in context.groups],
    )
    return context


def final_summary(
    ollama: OllamaClient,
    context: SummaryContext,
    summaries: list[str],
    config: SummaryConfig,
    logger: SessionLogger,
) -> GenerateResult:
    say(f"📝 Asking {config.model} for final markdown summary...")
    prompt = build_final_prompt(
        context,
        summaries,
        config.final_prompt,
        config.final_extra_instructions,
        config.title,
    )
    options = OllamaOptions(
        num_ctx=config.num_ctx,
        num_predict=config.final_tokens,
        temperature=config.temperature,
        timeout=config.timeout,
    )
    logger.request("summary_final_request", prompt, model=config.model, options=options)
    result = ollama.generate_with_stats(prompt=prompt, options=options)
    logger.response(
        "summary_final_response",
        result.text,
        prompt_tokens=result.prompt_tokens,
        output_tokens=result.output_tokens,
    )
    usage = result.usage_text()
    if usage:
        say(f"📊 Final summary tokens: {usage}")
    return result


def publish_summary(
    repo_root: Path,
    github: GitHubClient,
    pr_url: str | None,
    result: dict[str, str],
) -> None:
    url = pr_url or github.current_branch_pull_request_url()
    edit_pr(repo_root, url, result.get("title"), result["body"])


def handle_summary_error(logger: SessionLogger, error: Exception) -> None:
    message = f"{type(error).__name__}: {error}"
    logger.log("summary_error", error=message)
    say(f"❌ Summary failed: {message}")


def collect_summary_context(repo_root: Path, config: SummaryConfig) -> SummaryContext:
    context = collect_work_context(
        repo_root,
        max_group_chars=config.max_group_chars,
        max_groups=config.max_groups,
        ignores=config.ignores,
        unified=20,
        truncation_marker="[group diff truncated]",
        runner=run,
    )
    groups = [
        SummaryGroup(group.name, group.paths, group.diff, group.trimmed, group.truncations)
        for group in context.groups
    ]
    summary_context = SummaryContext(
        base=context.base,
        branch=context.branch,
        commits=context.commits,
        stat=context.stat,
        name_status=context.name_status,
        ignores=context.ignores,
        groups=groups,
    )
    say(context_ready_message(summary_context, "summary"))
    for message in truncation_messages(summary_context):
        say(message)
    return summary_context


def summarize_groups(
    ollama: OllamaClient,
    context: SummaryContext,
    config: SummaryConfig,
    logger: SessionLogger | None = None,
) -> list[str]:
    if len(context.groups) == 1:
        say(single_group_message("summary"))
        return []

    say(f"🧩 Summarizing {len(context.groups)} groups with {config.workers} parallel workers...")

    def summarize(group: SummaryGroup) -> str:
        prompt = build_group_prompt(
            context,
            group,
            config.split_group_prompt,
            config.split_group_extra_instructions,
        )
        options = OllamaOptions(
            num_ctx=config.num_ctx,
            num_predict=config.summary_tokens,
            temperature=config.temperature,
            timeout=config.timeout,
        )
        if logger:
            logger.request(
                "summary_group_request",
                prompt,
                group=group_log(group),
                options=options,
            )
        try:
            output = ollama.generate_with_stats(prompt, options)
        except Exception as error:
            if logger:
                logger.log(
                    "summary_group_error",
                    group=group.name,
                    error=f"{type(error).__name__}: {error}",
                )
            raise
        if logger:
            logger.response(
                "summary_group_response",
                output.text,
                group=group.name,
                prompt_tokens=output.prompt_tokens,
                output_tokens=output.output_tokens,
            )
        usage = output.usage_text()
        if usage:
            say(f"📊 Summary group {group.name}: {usage}")
        return group_summary_text(output.text, group.name)

    summaries = run_workers(context.groups, config.workers, summarize)
    summaries.sort()
    return summaries


def group_log(group: SummaryGroup | WorkGroup) -> dict[str, object]:
    return {
        "name": group.name,
        "paths": group.paths,
        "trimmed": group.trimmed,
        "diff_chars": len(group.diff),
        "truncations": group.truncations,
    }


def build_group_prompt(
    context: SummaryContext,
    group: SummaryGroup,
    prompt_template: str = "",
    extra_instructions: str = "",
) -> str:
    return render_configured_prompt(
        default_template=DEFAULT_GROUP_PROMPT_TEMPLATE,
        prompt_template=prompt_template,
        values=work_group_values(context, group),
        extra_instructions=extra_instructions,
    )


def build_final_prompt(
    context: SummaryContext,
    summaries: list[str],
    prompt_template: str = "",
    extra_instructions: str = "",
    title: TitleConfig | None = None,
) -> str:
    title_config = title or default_title_config()
    values = {
        "branch": context.branch,
        "base": context.base,
        "commits": context.commits,
        "stat": context.stat,
        "area_summaries": "\n".join(summaries),
        "title_prefixes": ", ".join(title_config.prefixes),
        "title_update": str(title_config.update).lower(),
        "title_enforce_prefix": str(title_config.enforce_prefix).lower(),
        "title_shape": "TITLE: feat: short clear title\n\n" if title_config.update else "",
        "title_rules": title_rules(title_config),
    }
    if prompt_template.strip():
        return render_configured_prompt(
            default_template=DEFAULT_FINAL_PROMPT_TEMPLATE,
            prompt_template=prompt_template,
            values=values,
            extra_instructions=extra_instructions,
        )
    return render_configured_prompt(
        default_template=DEFAULT_FINAL_PROMPT_TEMPLATE,
        prompt_template="",
        values=values,
        extra_instructions=extra_instructions,
    )


def group_summary_text(text: str, fallback_area: str) -> str:
    body = text.strip()
    if not body:
        body = "- No useful summary returned for the group."
    return f"### {fallback_area}\n\n{body}"


def parse_summary_result(text: str, title: TitleConfig | None = None) -> dict[str, str]:
    title_config = title or default_title_config()
    title = ""
    body_lines = []
    in_body = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("TITLE:"):
            title = stripped.removeprefix("TITLE:").strip()
            continue
        if stripped == "BODY:":
            in_body = True
            continue
        if in_body:
            body_lines.append(line)

    body = clean_summary_body("\n".join(body_lines))
    if title_config.update and not title:
        raise ValueError(f"model returned unusable title/body\n\nResponse:\n{text}")
    if not body:
        raise ValueError(f"model returned unusable title/body\n\nResponse:\n{text}")
    if title and title_config.enforce_prefix and not title.startswith(tuple(title_config.prefixes)):
        raise ValueError(f"model returned title without allowed prefix: {title}")
    result = {"body": body}
    if title_config.update:
        result["title"] = title
    return result


def clean_summary_body(text: str) -> str:
    parts = []
    blank = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            blank = True
            continue
        if parts and blank:
            parts.append("")
        parts.append(line)
        blank = False
    return "\n".join(parts).strip()


def edit_pr(repo_root: Path, url: str, title: str | None, body: str) -> None:
    with tempfile.NamedTemporaryFile("w", delete=False) as file:
        file.write(body)
        body_file = file.name
    try:
        cmd = ["gh", "pr", "edit", url, "--body-file", body_file]
        if title:
            cmd.extend(["--title", title])
        run(cmd, repo_root)
    finally:
        Path(body_file).unlink(missing_ok=True)


def default_title_config() -> TitleConfig:
    from shippy.config import TitleConfig

    return TitleConfig(
        update=True,
        enforce_prefix=True,
        prefixes=DEFAULT_TITLE_PREFIXES,
    )


def title_rules(title: TitleConfig) -> str:
    if not title.update:
        return "- Output starts with BODY:."
    if title.enforce_prefix:
        return "- Output starts with TITLE: using one of these prefixes: " + ", ".join(
            title.prefixes
        )
    return "- Output starts with TITLE: followed by a short title."
