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
    format: dict[str, object] | None = None


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
        if options.format:
            payload["format"] = options.format
        request = urllib.request.Request(
            f"{self.api_base}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=options.timeout) as response:
                data = json.loads(response.read().decode())
        except urllib.error.URLError as error:
            raise OllamaError(f"Ollama request failed: {error}") from error

        return str(data["response"]).strip()
