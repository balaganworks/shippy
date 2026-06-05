import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shippy.cli import init_config
from shippy.config import load_review_config, load_summary_config
from shippy.errors import ConfigError, OllamaError
from shippy.github import GitHubClient
from shippy.log import SessionLogger
from shippy.ollama import OllamaClient, OllamaOptions
from shippy.prompts import render_prompt

CONFIG = """
model = "ollama/gemma4:e4b"
ollama_url = "http://localhost:11434"
ignores = ["**/dist/**"]

[summary]
context_window = 8192
max_group_chars = 16000
max_groups = 15
temperature = 0.1
workers = 5
timeout_seconds = 420

[title]
update = true
enforce_prefix = true
prefixes = ["feat:", "fix:"]

[review]
context_window = 8192
max_group_chars = 16000
max_groups = 12
temperature = 0.05
workers = 4
timeout_seconds = 420

[prompts]
summary_split_group = "group {{area}}"
summary_final = "final {{area_summaries}}"
review_split_group = "review group {{area}}"
review_final = "custom {{diff}}"

[extra_instructions]
summary_split_group = "focus on API changes"
summary_final = "keep risk short"
review_split_group = "inspect group carefully"
review_final = "ignore generated docs"
"""


class ConfigTest(unittest.TestCase):
    def test_init_config_writes_example_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = init_config(Path(tmp))

            self.assertEqual(path, Path(tmp) / ".shippy.toml")
            self.assertIn("summary_split_group", path.read_text(encoding="utf-8"))

    def test_init_config_refuses_to_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".shippy.toml"
            path.write_text("existing", encoding="utf-8")

            with self.assertRaisesRegex(Exception, "config already exists"):
                init_config(Path(tmp))

    def test_load_review_config_from_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            (repo_root / ".shippy.toml").write_text(CONFIG, encoding="utf-8")

            config = load_review_config(repo_root)

            self.assertEqual(config.model, "gemma4:e4b")
            self.assertEqual(config.api_base, "http://localhost:11434")
            self.assertEqual(config.num_ctx, 8192)
            self.assertEqual(config.max_group_chars, 16000)
            self.assertEqual(config.max_groups, 12)
            self.assertEqual(config.group_tokens, 1024)
            self.assertEqual(config.num_predict, 2048)
            self.assertEqual(config.workers, 4)
            self.assertEqual(config.ignores, ["**/dist/**"])
            self.assertEqual(config.split_group_prompt, "review group {{area}}")
            self.assertEqual(config.final_prompt, "custom {{diff}}")
            self.assertEqual(config.split_group_extra_instructions, "inspect group carefully")
            self.assertEqual(config.final_extra_instructions, "ignore generated docs")
            self.assertEqual(config.debug.log_dir, "logs")
            self.assertFalse(config.debug.verbose)

    def test_load_summary_config_from_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            (repo_root / ".shippy.toml").write_text(CONFIG, encoding="utf-8")

            config = load_summary_config(repo_root)

            self.assertEqual(config.model, "gemma4:e4b")
            self.assertEqual(config.summary_tokens, 1024)
            self.assertEqual(config.final_tokens, 2048)
            self.assertEqual(config.split_group_prompt, "group {{area}}")
            self.assertEqual(config.final_prompt, "final {{area_summaries}}")
            self.assertEqual(config.title.prefixes, ["feat:", "fix:"])
            self.assertEqual(config.split_group_extra_instructions, "focus on API changes")
            self.assertEqual(config.final_extra_instructions, "keep risk short")
            self.assertEqual(config.debug.log_dir, "logs")
            self.assertFalse(config.debug.verbose)

    def test_load_debug_config_from_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            (repo_root / ".shippy.toml").write_text(
                CONFIG
                + """
[debug]
log_dir = ".shippy/logs"
verbose = true
""",
                encoding="utf-8",
            )

            config = load_review_config(repo_root)

            self.assertEqual(config.debug.log_dir, ".shippy/logs")
            self.assertTrue(config.debug.verbose)

    def test_explicit_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "custom.toml"
            path.write_text(CONFIG, encoding="utf-8")

            config = load_review_config(Path(tmp), path)

            self.assertEqual(config.final_prompt, "custom {{diff}}")

    def test_invalid_prompts_config_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            (repo_root / ".shippy.toml").write_text(
                """
model = "gemma4:e4b"
ollama_url = "http://localhost:11434"
ignores = []
prompts = []

[review]
max_group_chars = 1
temperature = 0.1
timeout_seconds = 3
""",
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError):
                load_review_config(repo_root)

    def test_missing_config_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ConfigError):
            load_review_config(Path(tmp))


class HelpersTest(unittest.TestCase):
    def test_render_prompt_replaces_known_tokens(self) -> None:
        self.assertEqual(
            render_prompt(
                "review {{branch}} {{diff}}",
                {"branch": "feat/x", "diff": "diff --git"},
            ),
            "review feat/x diff --git",
        )

    def test_current_branch_pr_url_uses_single_match(self) -> None:
        def fake_run(cmd: list[str], cwd: Path) -> str:
            if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return "feat/x"
            return json.dumps([{"number": 1, "title": "one", "url": "https://example.test/1"}])

        with patch("shippy.github.run", fake_run):
            url = GitHubClient(Path(".")).current_branch_pull_request_url()

        self.assertEqual(url, "https://example.test/1")

    def test_current_branch_pr_url_uses_first_match_when_multiple(self) -> None:
        def fake_run(cmd: list[str], cwd: Path) -> str:
            if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return "feat/x"
            return json.dumps(
                [
                    {"number": 1, "title": "one", "url": "https://example.test/1"},
                    {"number": 2, "title": "two", "url": "https://example.test/2"},
                ]
            )

        with patch("shippy.github.run", fake_run):
            url = GitHubClient(Path(".")).current_branch_pull_request_url()

        self.assertEqual(url, "https://example.test/1")

    def test_current_branch_pr_url_fails_when_none(self) -> None:
        def fake_run(cmd: list[str], cwd: Path) -> str:
            if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return "feat/x"
            return "[]"

        with patch("shippy.github.run", fake_run), self.assertRaises(ValueError):
            GitHubClient(Path(".")).current_branch_pull_request_url()

    def test_session_logger_writes_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logger = SessionLogger(Path(tmp), "summary", ".shippy/logs")

            logger.request(
                "summary_group_request",
                "line one\nline two",
                model="gemma4:e4b",
                options={"num_ctx": 8192},
            )

            log_file = next((Path(tmp) / ".shippy" / "logs").glob("shippy_*_summary.log"))
            line = log_file.read_text(encoding="utf-8").strip()
            self.assertIn("Summary Group Request", line)
            self.assertIn("Model: gemma4:e4b", line)
            self.assertIn("Num Ctx: 8192", line)
            self.assertIn("Prompt Chars: 17", line)
            self.assertNotIn("line one", line)
            self.assertNotIn("\\n", line)

    def test_session_logger_keeps_last_ten_action_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "logs"
            log_dir.mkdir()
            for index in range(12):
                (log_dir / f"shippy_20260101_0000{index:02}_review.log").write_text(
                    "old",
                    encoding="utf-8",
                )
            for index in range(12):
                (log_dir / f"shippy_20260101_0000{index:02}_summary.log").write_text(
                    "old",
                    encoding="utf-8",
                )

            SessionLogger(Path(tmp), "review", "logs")

            self.assertEqual(len(list(log_dir.glob("shippy_*_review.log"))), 10)
            self.assertEqual(len(list(log_dir.glob("shippy_*_summary.log"))), 12)


class OllamaTest(unittest.TestCase):
    def test_generate_sends_configured_options(self) -> None:
        captured = {}

        class Response:
            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {"response": "ok", "prompt_eval_count": 12, "eval_count": 3}
                ).encode()

        def fake_urlopen(request: object, timeout: int) -> Response:
            request_data = request.data
            captured["timeout"] = timeout
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request_data.decode())
            return Response()

        client = OllamaClient("http://localhost:11434", "gemma4:e4b")

        with patch("urllib.request.urlopen", fake_urlopen):
            result = client.generate_with_stats(
                "prompt",
                OllamaOptions(
                    num_ctx=8192,
                    num_predict=1800,
                    temperature=0.05,
                    timeout=420,
                ),
            )

        self.assertEqual(result.text, "ok")
        self.assertEqual(result.usage_text(), "input 12, output 3")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(captured["url"], "http://localhost:11434/api/generate")
        self.assertEqual(captured["timeout"], 420)
        self.assertEqual(captured["payload"]["prompt"], "prompt")
        self.assertEqual(captured["payload"]["options"]["num_ctx"], 8192)
        self.assertEqual(captured["payload"]["options"]["num_predict"], 1800)
        self.assertEqual(captured["payload"]["options"]["temperature"], 0.05)

    def test_generate_wraps_timeout(self) -> None:
        client = OllamaClient("http://localhost:11434", "gemma4:e4b")

        def fake_urlopen(_request: object, timeout: int) -> object:
            raise TimeoutError("timed out")

        with (
            patch("urllib.request.urlopen", fake_urlopen),
            patch("time.sleep", lambda _seconds: None),
            self.assertRaisesRegex(OllamaError, "timed out after 3s"),
        ):
            client.generate_with_stats(
                "prompt",
                OllamaOptions(
                    num_ctx=8192,
                    num_predict=1800,
                    temperature=0.05,
                    timeout=3,
                ),
            )

    def test_generate_retries_timeout_then_succeeds(self) -> None:
        calls = 0

        class Response:
            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"response": "ok", "eval_count": 3}).encode()

        def fake_urlopen(_request: object, timeout: int) -> object:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("timed out")
            return Response()

        client = OllamaClient("http://localhost:11434", "gemma4:e4b")

        with (
            patch("urllib.request.urlopen", fake_urlopen),
            patch("time.sleep", lambda _seconds: None),
        ):
            result = client.generate_with_stats(
                "prompt",
                OllamaOptions(
                    num_ctx=8192,
                    num_predict=1800,
                    temperature=0.05,
                    timeout=3,
                ),
            )

        self.assertEqual(result.text, "ok")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(calls, 2)

    def test_generate_rejects_empty_response(self) -> None:
        class Response:
            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"response": "   ", "eval_count": 1024}).encode()

        client = OllamaClient("http://localhost:11434", "gemma4:e4b")

        with (
            patch("urllib.request.urlopen", lambda *_args, **_kwargs: Response()),
            patch("time.sleep", lambda _seconds: None),
            self.assertRaisesRegex(OllamaError, "empty response"),
        ):
            client.generate_with_stats(
                "prompt",
                OllamaOptions(
                    num_ctx=8192,
                    num_predict=1800,
                    temperature=0.05,
                    timeout=3,
                ),
            )

    def test_generate_retries_empty_response_then_succeeds(self) -> None:
        calls = 0

        class Response:
            def __init__(self, response: str) -> None:
                self.response = response

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"response": self.response, "eval_count": 3}).encode()

        def fake_urlopen(_request: object, timeout: int) -> object:
            nonlocal calls
            calls += 1
            if calls < 3:
                return Response("   ")
            return Response("ok")

        client = OllamaClient("http://localhost:11434", "gemma4:e4b")

        with (
            patch("urllib.request.urlopen", fake_urlopen),
            patch("time.sleep", lambda _seconds: None),
        ):
            result = client.generate_with_stats(
                "prompt",
                OllamaOptions(
                    num_ctx=8192,
                    num_predict=1800,
                    temperature=0.05,
                    timeout=3,
                ),
            )

        self.assertEqual(result.text, "ok")
        self.assertEqual(result.attempts, 3)
        self.assertEqual(calls, 3)


if __name__ == "__main__":
    unittest.main()
