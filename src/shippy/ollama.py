"""Small Ollama HTTP client."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

from shippy.errors import OllamaError


@dataclass(frozen=True)
class OllamaOptions:
    num_ctx: int
    num_predict: int
    temperature: float
    timeout: int


@dataclass(frozen=True)
class GenerateResult:
    text: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None

    def usage_text(self) -> str:
        parts = []
        if self.prompt_tokens is not None:
            parts.append(f"input {self.prompt_tokens}")
        if self.output_tokens is not None:
            parts.append(f"output {self.output_tokens}")
        return ", ".join(parts)


class OllamaClient:
    def __init__(self, api_base: str, model: str) -> None:
        self.api_base = api_base.rstrip("/")
        self.model = model

    def assert_model_available(self) -> None:
        result = subprocess.run(
            ["ollama", "list"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "ollama list failed"
            raise OllamaError(message)
        names = {line.split()[0] for line in result.stdout.splitlines()[1:] if line.split()}
        if self.model not in names:
            raise OllamaError(
                f"missing configured model: {self.model}\n"
                f"current Ollama provider can install it with: ollama pull {self.model}"
            )

    def generate(self, prompt: str, options: OllamaOptions) -> str:
        return self.generate_with_stats(prompt, options).text

    def generate_with_stats(self, prompt: str, options: OllamaOptions) -> GenerateResult:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": options.temperature,
                "num_ctx": options.num_ctx,
                "num_predict": options.num_predict,
            },
        }
        request = urllib.request.Request(
            f"{self.api_base}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=options.timeout) as response:
                data = json.loads(response.read().decode())
        except TimeoutError as error:
            raise OllamaError(
                f"Ollama request timed out after {options.timeout}s "
                f"(input {len(prompt)} chars, num_ctx {options.num_ctx}, "
                f"num_predict {options.num_predict})"
            ) from error
        except urllib.error.URLError as error:
            raise OllamaError(f"Ollama request failed: {error}") from error

        return GenerateResult(
            text=str(data["response"]).strip(),
            prompt_tokens=_int_or_none(data.get("prompt_eval_count")),
            output_tokens=_int_or_none(data.get("eval_count")),
        )


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    return int(value)
