"""Configuration loading for Shippy."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shippy.errors import ConfigError
from shippy.summary.constants import DEFAULT_TITLE_PREFIXES

DEFAULT_CONTEXT_WINDOW = 8192
DEFAULT_GROUP_OUTPUT_TOKENS = 1024
DEFAULT_FINAL_OUTPUT_TOKENS = 2048
DEFAULT_MAX_GROUPS = 12
DEFAULT_WORKERS = 4


@dataclass(frozen=True)
class ReviewConfig:
    model: str
    api_base: str
    num_ctx: int
    max_group_chars: int
    max_groups: int
    group_tokens: int
    num_predict: int
    temperature: float
    workers: int
    timeout: int
    ignores: list[str]
    split_group_prompt: str
    final_prompt: str
    split_group_extra_instructions: str
    final_extra_instructions: str

    @property
    def prompt(self) -> str:
        return self.final_prompt

    @property
    def extra_instructions(self) -> str:
        return self.final_extra_instructions


@dataclass(frozen=True)
class TitleConfig:
    update: bool
    enforce_prefix: bool
    prefixes: list[str]


@dataclass(frozen=True)
class SummaryConfig:
    model: str
    api_base: str
    num_ctx: int
    max_group_chars: int
    max_groups: int
    summary_tokens: int
    final_tokens: int
    temperature: float
    workers: int
    timeout: int
    ignores: list[str]
    title: TitleConfig
    split_group_prompt: str
    final_prompt: str
    split_group_extra_instructions: str
    final_extra_instructions: str

    @property
    def group_prompt(self) -> str:
        return self.split_group_prompt

    @property
    def group_extra_instructions(self) -> str:
        return self.split_group_extra_instructions


def _ollama_model(model: str) -> str:
    return model.removeprefix("ollama/")


def load_review_config(
    repo_root: Path,
    config_path: Path | None = None,
) -> ReviewConfig:
    """Load review config from .shippy.toml."""
    raw = _load_raw_config(repo_root, config_path)

    try:
        review = raw["review"]
        ignores = raw["ignores"]
        if not isinstance(review, dict):
            raise ConfigError("config key 'review' must be a mapping")
        if not isinstance(ignores, list):
            raise ConfigError("config key 'ignores' must be a list")
        return ReviewConfig(
            model=_ollama_model(str(raw["model"])),
            api_base=str(raw["ollama_url"]).rstrip("/"),
            num_ctx=int(
                review.get("context_window", raw.get("context_window", DEFAULT_CONTEXT_WINDOW))
            ),
            max_group_chars=_int_value(review, "max_group_chars", "max_diff_chars"),
            max_groups=int(review.get("max_groups", DEFAULT_MAX_GROUPS)),
            group_tokens=int(
                review.get(
                    "split_group_output_tokens",
                    review.get(
                        "group_output_tokens",
                        review.get("group_tokens", DEFAULT_GROUP_OUTPUT_TOKENS),
                    ),
                )
            ),
            num_predict=int(
                review.get(
                    "final_output_tokens",
                    review.get("output_tokens", DEFAULT_FINAL_OUTPUT_TOKENS),
                )
            ),
            temperature=float(review.get("temperature", 0.05)),
            workers=int(review.get("workers", DEFAULT_WORKERS)),
            timeout=int(review["timeout_seconds"]),
            ignores=[str(pattern) for pattern in ignores],
            split_group_prompt=str(_prompt_value(raw, "review_split_group", "review_group")),
            final_prompt=str(_prompt_value(raw, "review_final", "review")),
            split_group_extra_instructions=str(
                _extra_instruction_value(raw, "review_split_group", "review_group")
            ),
            final_extra_instructions=str(_extra_instruction_value(raw, "review_final", "review")),
        )
    except KeyError as error:
        raise ConfigError(f"missing config key: {error}") from error


def load_summary_config(
    repo_root: Path,
    config_path: Path | None = None,
) -> SummaryConfig:
    """Load summary config from .shippy.toml."""
    raw = _load_raw_config(repo_root, config_path)

    try:
        summary = raw["summary"]
        ignores = raw["ignores"]
        if not isinstance(summary, dict):
            raise ConfigError("config key 'summary' must be a mapping")
        if not isinstance(ignores, list):
            raise ConfigError("config key 'ignores' must be a list")
        prompts = _prompts(raw)
        extra_instructions = _extra_instructions(raw)
        return SummaryConfig(
            model=_ollama_model(str(raw["model"])),
            api_base=str(raw["ollama_url"]).rstrip("/"),
            num_ctx=int(
                summary.get("context_window", raw.get("context_window", DEFAULT_CONTEXT_WINDOW))
            ),
            max_group_chars=int(summary["max_group_chars"]),
            max_groups=int(summary.get("max_groups", DEFAULT_MAX_GROUPS)),
            summary_tokens=int(
                summary.get(
                    "split_group_output_tokens",
                    summary.get("summary_tokens", DEFAULT_GROUP_OUTPUT_TOKENS),
                )
            ),
            final_tokens=int(
                summary.get(
                    "final_output_tokens",
                    summary.get("final_tokens", DEFAULT_FINAL_OUTPUT_TOKENS),
                )
            ),
            temperature=float(summary.get("temperature", 0.1)),
            workers=int(summary.get("workers", DEFAULT_WORKERS)),
            timeout=int(summary["timeout_seconds"]),
            ignores=[str(pattern) for pattern in ignores],
            title=_title_config(raw),
            split_group_prompt=str(_prompt_value(raw, "summary_split_group", "summary_group")),
            final_prompt=str(prompts.get("summary_final") or ""),
            split_group_extra_instructions=str(
                _extra_instruction_value(raw, "summary_split_group", "summary_group")
            ),
            final_extra_instructions=str(extra_instructions.get("summary_final") or ""),
        )
    except KeyError as error:
        raise ConfigError(f"missing config key: {error}") from error


def _load_raw_config(repo_root: Path, config_path: Path | None) -> dict[str, Any]:
    path = config_path or repo_root / ".shippy.toml"
    if not path.exists():
        raise ConfigError(f"missing config file: {path}")

    with path.open("rb") as config_file:
        loaded = tomllib.load(config_file)
    if not isinstance(loaded, dict):
        raise ConfigError(f"config must be a mapping: {path}")
    return loaded


def _prompts(raw: dict[str, Any]) -> dict[str, Any]:
    prompts = raw.get("prompts", {})
    if not isinstance(prompts, dict):
        raise ConfigError("config key 'prompts' must be a mapping")
    return prompts


def _extra_instructions(raw: dict[str, Any]) -> dict[str, Any]:
    extra_instructions = raw.get("extra_instructions", {})
    if not isinstance(extra_instructions, dict):
        raise ConfigError("config key 'extra_instructions' must be a mapping")
    return extra_instructions


def _prompt_value(raw: dict[str, Any], name: str, fallback: str = "") -> Any:
    prompts = _prompts(raw)
    return prompts.get(name) or (prompts.get(fallback) if fallback else "") or ""


def _extra_instruction_value(raw: dict[str, Any], name: str, fallback: str = "") -> Any:
    extra_instructions = _extra_instructions(raw)
    return (
        extra_instructions.get(name) or (extra_instructions.get(fallback) if fallback else "") or ""
    )


def _int_value(raw: dict[str, Any], name: str, fallback: str = "") -> int:
    if name in raw:
        return int(raw[name])
    if fallback and fallback in raw:
        return int(raw[fallback])
    raise KeyError(name)


def _title_config(raw: dict[str, Any]) -> TitleConfig:
    title = raw.get("title", {})
    if not isinstance(title, dict):
        raise ConfigError("config key 'title' must be a mapping")
    prefixes = title.get("prefixes", DEFAULT_TITLE_PREFIXES)
    if not isinstance(prefixes, list) or not prefixes:
        raise ConfigError("config key 'title.prefixes' must be a non-empty list")
    return TitleConfig(
        update=bool(title.get("update", True)),
        enforce_prefix=bool(title.get("enforce_prefix", True)),
        prefixes=[str(prefix) for prefix in prefixes],
    )
