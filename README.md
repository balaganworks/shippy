<h1 align="center">🚢 Shippy</h1>

<p align="center">
  <a href="https://pypi.org/project/shippy-ai/"><img alt="PyPI" src="https://img.shields.io/badge/package-shippy--ai-teal"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-green"></a>
  <a href=".github/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/badge/ci-github--actions-blue"></a>
</p>

<p align="center"><strong>AI pull-request summaries and reviews, posted straight to your git provider.</strong></p>

`shippy` is a CLI reviewer for pull requests. It reads the real PR context,
splits large diffs into focused worker groups, asks the configured AI platform
for summary/review output, and publishes clean GitHub updates without comment
spam.

Use it to turn messy PRs into clear title/body updates and one sticky review
comment. Today it supports Ollama + GitHub. More AI platforms and Git platforms
are the next expansion path.

---

<h2 align="center">📌 What It Does</h2>

| Workflow | What Shippy Does |
| --- | --- |
| **Summary** | Generates a PR title and body from commits, changed files, diff stat, and grouped diff context. |
| **Review** | Reviews focused file groups in parallel, then merges findings into one sticky Markdown comment. |
| **Context** | Collects branch/base data, commits, changed files, diff stats, ignored paths, and model settings. |
| **Publishing** | Updates GitHub through `gh`; review comments use `<!-- shippy-review -->` so reruns update one comment. |

---

<h2 align="center">🧭 Why It Exists</h2>

`shippy` is not a replacement for human review. It catches the boring and
expensive-to-miss stuff before people spend attention on it:

- risky diffs
- unclear PR intent
- missing tests
- generated-file noise
- accidental large changes
- suspicious cleanup/refactor mistakes

Goal: **make every PR easier to understand and safer to ship.**

---

<h2 align="center">✨ Highlights</h2>

| Feature | Detail |
| --- | --- |
| 📝 PR summaries | Clear title/body updates from actual repository and PR context. |
| 🔍 PR reviews | Finds bugs, risks, missing tests, and concrete cleanup opportunities. |
| 📌 Sticky comments | One GitHub review comment, updated on rerun. |
| ⚡ Split workers | Large PRs are split into focused groups and processed in parallel. |
| 🧹 Ignore rules | Lockfiles, generated files, build outputs, and noisy paths can be skipped. |
| 🛠 CLI-first | Works locally, from scripts, and from release workflows. |

---

<h2 align="center">🤖 Supported Platforms</h2>

| Type | Supported Now | Planned |
| --- | --- | --- |
| **AI platform** | Ollama | API-key providers, hosted model APIs, provider presets |
| **Git platform** | GitHub through `gh` | GitLab, Bitbucket, and other review platforms |

---

<h2 align="center">🚀 Quick Start</h2>

Requirements:

- Python 3.11+
- `git`
- GitHub CLI authenticated with `gh auth login`
- Ollama running locally with a pulled model

```sh
ollama serve
ollama pull gemma4:e4b
pip install shippy-ai
shippy init
shippy summary
shippy review
```

From a local checkout:

```sh
uv run -m shippy.cli init
uv run -m shippy.cli summary
uv run -m shippy.cli review
```

Run Shippy from anywhere inside a Git work tree. It discovers the repository
root automatically.

---

<h2 align="center">⚙️ Configuration</h2>

`shippy init` creates `.shippy.toml` at the Git repository root and refuses to
overwrite an existing config.

Minimal shape:

```toml
model = "gemma4:e4b"
ollama_url = "http://localhost:11434"

ignores = [
  "**/go.sum",
  "**/package-lock.json",
  "**/dist/**",
  "**/build/**",
  "**/.next/**",
  "**/coverage/**",
  "graphify-out/**",
]

[summary]
context_window = 16384
max_group_chars = 32000
max_groups = 12
workers = 4
temperature = 0.1
timeout_seconds = 420

[review]
context_window = 16384
max_group_chars = 32000
max_groups = 12
workers = 4
temperature = 0.05
timeout_seconds = 420

[title]
update = true
enforce_prefix = true
prefixes = ["feat:", "task:", "fix:", "hotfix:", "chore:", "docs:", "refactor:"]

[prompts]
summary_split_group = ""
summary_final = ""
review_split_group = ""
review_final = ""
```

### 🧠 Context And Limits

- `context_window` is provider context per model call.
- Shippy tries to send the whole PR to one worker first.
- `max_group_chars` is the diff size cap before Shippy splits into groups.
- `max_group_chars` is measured in characters, not tokens.
- `32000` diff chars is roughly several thousand tokens for code.
- Output caps default to `1024` tokens for split-group workers and `2048` tokens
  for final synthesis.

Override output caps only when the model needs longer answers:

```toml
[review]
split_group_output_tokens = 1024
final_output_tokens = 2048
```

See the full editable config template here: [`src/shippy/templates/.shippy.toml`](src/shippy/templates/.shippy.toml).

### 🧩 Prompt Overrides

Leave prompt fields empty to use Shippy defaults. Set a field to replace that
prompt completely. Use `[extra_instructions]` to keep the default prompt and
append custom rules.

`split_group` means: **prompt for one chunk of changed files**.

Supported prompt tokens:

- `summary_split_group`: `{{area}}`, `{{branch}}`, `{{base}}`, `{{ignored_paths}}`, `{{files}}`, `{{diff}}`
- `summary_final`: `{{branch}}`, `{{base}}`, `{{commits}}`, `{{stat}}`, `{{area_summaries}}`, `{{title_prefixes}}`, `{{title_update}}`, `{{title_enforce_prefix}}`, `{{title_shape}}`, `{{title_rules}}`
- `review_split_group`: `{{area}}`, `{{pr_title}}`, `{{pr_url}}`, `{{pr_body}}`, `{{branch}}`, `{{base}}`, `{{commits}}`, `{{stat}}`, `{{files}}`, `{{diff}}`, `{{trim_note}}`
- `review_final`: `{{pr_title}}`, `{{pr_url}}`, `{{pr_body}}`, `{{branch}}`, `{{base}}`, `{{commits}}`, `{{stat}}`, `{{changed_files}}`, `{{diff}}`, `{{area_reviews}}`, `{{trim_note}}`

---

<h2 align="center">🧪 Commands</h2>

```sh
shippy init
shippy summary
shippy review
shippy --pr-url "$PR_URL" summary
shippy --config ./custom.toml --pr-url "$PR_URL" review
shippy --help
```

---

<h2 align="center">🧾 Example Review Output</h2>

```md
## AI Review

### Verdict
✅ Pass: no blocking issue visible.

### Tests
- Unit tests were not visible in PR context.
```

---

<h2 align="center">🔒 Privacy</h2>

Current Ollama + GitHub support talks to:

- your local Git repository
- GitHub through `gh`
- your configured Ollama server

Your prompt is sent to the AI platform endpoint you configure.

---

<h2 align="center">🧰 Development</h2>

For contributors cloning this repo, use the root Taskfile:

```sh
task prereq
task format
task check
task publish:check
```

---

<h2 align="center">🤝 Contributing</h2>

PRs are welcome, especially for:

- more AI platforms
- more Git platforms
- more features
- better usability
- better prompts
- cleaner Git platform comment behavior
- config improvements
- model compatibility fixes
- tests around diff collection and output formatting

Before opening a PR:

```sh
task format
task check
task publish:check
```

---

<h2 align="center">📄 License</h2>

MIT
