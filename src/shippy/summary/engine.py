"""PR title and body generation."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from shippy.git import run
from shippy.github import GitHubClient
from shippy.ollama import OllamaClient, OllamaOptions
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
    parse_name_status,
    render_configured_prompt,
    run_workers,
    work_group_values,
)

if TYPE_CHECKING:
    from shippy.config import SummaryConfig, TitleConfig


@dataclass(frozen=True)
class SummaryGroup(WorkGroup):
    pass


@dataclass(frozen=True)
class SummaryContext(WorkContext):
    groups: list[SummaryGroup]


def summarize_pull_request(repo_root: Path, pr_url: str | None, config: SummaryConfig) -> None:
    github = GitHubClient(repo_root)
    ollama = OllamaClient(config.api_base, config.model)
    ollama.assert_model_available()

    url = pr_url or github.current_branch_pull_request_url()
    say("Collecting PR summary context...")
    context = collect_summary_context(repo_root, config)
    summaries = summarize_groups(ollama, context, config)
    final = ollama.generate(
        prompt=build_final_prompt(
            context,
            summaries,
            config.final_prompt,
            config.final_extra_instructions,
            config.title,
        ),
        options=OllamaOptions(
            num_ctx=config.num_ctx,
            num_predict=config.final_tokens,
            temperature=config.temperature,
            timeout=config.timeout,
            format=None,
        ),
    )
    result = parse_summary_result(final, config.title)
    edit_pr(repo_root, url, result.get("title"), result["body"])
    say("Updated PR title/body")


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
        SummaryGroup(group.name, group.paths, group.diff, group.trimmed) for group in context.groups
    ]
    file_count = len(parse_name_status(context.name_status))
    say(f"Context ready: {file_count} files across {len(groups)} groups")
    return SummaryContext(
        base=context.base,
        branch=context.branch,
        commits=context.commits,
        stat=context.stat,
        name_status=context.name_status,
        ignores=context.ignores,
        groups=groups,
    )


def summarize_groups(
    ollama: OllamaClient,
    context: SummaryContext,
    config: SummaryConfig,
) -> list[str]:
    say(f"Summarizing {len(context.groups)} groups with {config.workers} workers...")

    def summarize(group: SummaryGroup) -> str:
        output = ollama.generate(
            build_group_prompt(
                context,
                group,
                config.split_group_prompt,
                config.split_group_extra_instructions,
            ),
            OllamaOptions(
                num_ctx=config.num_ctx,
                num_predict=config.summary_tokens,
                temperature=config.temperature,
                timeout=config.timeout,
                format=None,
            ),
        )
        return group_summary_text(output, group.name)

    summaries = run_workers(context.groups, config.workers, summarize)
    summaries.sort()
    return summaries


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
