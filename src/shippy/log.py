"""Optional debug logging for model sessions."""

from __future__ import annotations

import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

RESET = "\033[0m"
DIM = "\033[2m"
CYAN = "\033[36m"
BOLD = "\033[1m"
GREEN = "\033[32m"


class SessionLogger:
    def __init__(
        self,
        repo_root: Path,
        action: str,
        log_dir: str = "logs",
        verbose: bool = False,
    ) -> None:
        self.action = action
        self.path = _log_path(repo_root, log_dir, action)
        self.verbose = verbose
        self._lock = threading.Lock()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _prune_logs(self.path.parent, action)

    @property
    def enabled(self) -> bool:
        return self.path is not None or self.verbose

    def log(self, event: str, **fields: Any) -> None:
        if not self.enabled:
            return
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "event": event,
            **fields,
        }
        text = _format_entry(entry)
        if self.path:
            with self._lock, self.path.open("a", encoding="utf-8") as file:
                file.write(text + "\n")
        if self.verbose:
            print(_color_entry(text, str(entry["event"])), flush=True)

    def request(
        self,
        event: str,
        prompt: str,
        *,
        model: str = "",
        group: dict[str, object] | None = None,
        options: object | None = None,
    ) -> None:
        self.log(
            event,
            model=model,
            **_flatten_group(group),
            **_flatten_options(options),
            prompt_chars=len(prompt),
        )

    def response(self, event: str, output: str, **fields: Any) -> None:
        self.log(
            event,
            **fields,
            output_chars=len(output),
            output_preview=output,
        )


def _log_path(repo_root: Path, log_dir: str, action: str) -> Path | None:
    if not log_dir:
        return None
    path = Path(log_dir).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path / f"shippy_{timestamp}_{action}.log"


def _prune_logs(log_dir: Path, action: str, keep: int = 10) -> None:
    logs = sorted(log_dir.glob(f"shippy_*_{action}.log"), reverse=True)
    for log in logs[keep:]:
        log.unlink(missing_ok=True)


def _format_entry(entry: dict[str, Any]) -> str:
    lines = [f"{entry['time']} {title_for_event(str(entry['event']))}"]
    for key, value in entry.items():
        if key in {"time", "event"}:
            continue
        if value in (None, "", [], {}):
            continue
        formatted = _format_value(value)
        formatted = formatted.replace("\n", "\n  ")
        lines.append(f"  {_title_key(key)}: {formatted}")
    return "\n".join(lines)


def _format_value(value: object) -> str:
    value = _json_default(value)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if item in ("", [], {}):
                continue
            parts.append(f"{_title_key(str(key))}: {_format_value(item)}")
        return "\n  ".join(parts)
    if isinstance(value, list):
        return ", ".join(_format_value(item) for item in value)
    return str(value)


def title_for_event(event: str) -> str:
    action, phase, direction = _event_parts(event)
    action_title = {"summary": "Summary", "review": "Review"}.get(action, action.title())
    phase_title = {"group": "Group", "final": "Final", "context": "Context"}.get(
        phase,
        phase.title(),
    )
    direction_title = {"request": "Request", "response": "Response"}.get(
        direction,
        direction.title(),
    )
    if phase == "context":
        return f"{action_title} Context"
    return f"{action_title} {phase_title} {direction_title}"


def _event_parts(event: str) -> tuple[str, str, str]:
    parts = event.split("_")
    action = parts[0] if parts else event
    phase = parts[1] if len(parts) > 1 else ""
    direction = parts[2] if len(parts) > 2 else ""
    return action, phase, direction


def _flatten_group(group: dict[str, object] | None) -> dict[str, object]:
    if not group:
        return {}
    return {
        "group": group.get("name"),
        "paths": group.get("paths"),
        "trimmed": group.get("trimmed"),
        "diff_chars": group.get("diff_chars"),
        "truncations": group.get("truncations"),
    }


def _flatten_options(options: object | None) -> dict[str, object]:
    if options is None:
        return {}
    value = _json_default(options)
    if not isinstance(value, dict):
        return {"options": value}
    return {str(key): item for key, item in value.items()}


def _title_key(key: str) -> str:
    return key.replace("_", " ").title()


def _color_entry(text: str, event: str) -> str:
    lines = text.splitlines()
    if not lines:
        return text
    color = _event_color(event)
    time, _, title = lines[0].partition(" ")
    lines[0] = f"{DIM}{time}{RESET} {color}{BOLD}{title}{RESET}"
    return "\n".join(_color_line(line, color) for line in lines)


def _color_line(line: str, color: str) -> str:
    if ": " not in line:
        return line
    key, value = line.split(": ", 1)
    return f"{color}{key}:{RESET} {value}"


def _event_color(event: str) -> str:
    if event.endswith("_request"):
        return GREEN
    if event.endswith("_response"):
        return CYAN
    if event.endswith("_context"):
        return GREEN
    return GREEN


def _json_default(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    return value
