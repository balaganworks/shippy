# 🚢 Shippy

**AI PR summaries and reviews, posted straight to GitHub.**

`shippy` currently inspects a GitHub pull request, summarizes the change,
reviews the diff, and publishes clean updates back to GitHub.

No noisy comment spam.  
No unclear PR walls.  
One focused tool that helps you ship cleaner PRs.

---

## 📌 What It Does

`shippy` collects real PR context:

- changed files
- commits
- diff stat
- branch/base data
- ignored/generated paths
- configured model settings

Then it runs split-group workers over focused chunks of the diff and merges the
results into either:

- 📝 a concise PR title and body
- 🔍 one Markdown review with verdict, findings, tests, and notes

The review comment is marked internally with:

```md
<!-- shippy-review -->
```

Future runs update that same comment instead of spamming the PR.

---

## 🧭 Philosophy

`shippy` is not trying to replace human review.

It catches boring stuff before humans spend attention on it:

- risky diffs
- unclear PR intent
- missing tests
- generated-file noise
- accidental large changes
- suspicious cleanup/refactor mistakes

Goal: **make every PR easier to understand and safer to ship.**

---

## ✨ Features

- 📝 **PR summaries** - generate a clear PR title and body from the actual diff.
- 🔍 **PR reviews** - find risks, missing tests, bugs, and cleanup opportunities.
- 📌 **Sticky GitHub comment** - creates or updates one Markdown review comment.
- ⚡ **Parallel split-group workers** - split large PRs into focused chunks.
- 🧹 **Ignore rules** - skip generated files, lockfiles, build outputs, and noisy paths.
- 🛠 **CLI-first** - easy to run locally, from scripts, or in release checks.
- 🐍 **Python-powered** - small package, simple config.

---

## 🤖 Supported Platforms

Current:

- ✅ **AI platform:** Ollama - local models through your configured Ollama server.
- ✅ **Git platform:** GitHub - PR metadata and sticky review comments through `gh`.

Planned:

- more AI platforms
- more Git platforms
- API-key AI providers
- hosted model APIs
- GitLab, Bitbucket, etc.
- platform presets
- richer model configuration

---

## 🚀 Quick Start

### Requirements

- Python 3.11+
- `git`
- GitHub CLI authenticated with:

```sh
gh auth login
```

- Ollama running locally:

```sh
ollama serve
```

- A pulled model, for example:

```sh
ollama pull gemma4:e4b
```

---

## 📦 Install

PyPI distribution name:

```sh
pip install shippy-ai
```

CLI name:

```sh
shippy --help
```

From a local checkout:

```sh
uv run -m shippy.cli --help
```

---

## ⚙️ Configuration

Create the example config in your repository:

```sh
shippy init
```

From a local checkout:

```sh
uv run -m shippy.cli init
```

This creates `.shippy.toml` at the Git repository root and refuses to overwrite
an existing config.

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
context_window = 8192
max_group_chars = 16000
max_groups = 12
workers = 4
temperature = 0.1
timeout_seconds = 420

[review]
context_window = 8192
max_group_chars = 16000
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

> **Important:** `summary` and `review` each have their own limits because they
> do different work. Summary writes PR metadata. Review hunts for bugs and risk.

### 🧠 Context And Limits

- `context_window` is provider context per model call.
- `max_group_chars` is a diff safety cap for each split-group worker.
- `max_group_chars` is measured in characters, not tokens.
- `16000` diff chars is roughly a few thousand tokens for code.
- Shippy keeps that below the `8192` token context window so prompts, file lists,
  metadata, and model output still fit.
- Output caps use defaults: `1024` tokens for split-group workers and `2048`
  tokens for final synthesis.

Only override output caps when the model needs longer answers:

```toml
[review]
split_group_output_tokens = 1024
final_output_tokens = 2048
```

### 🧩 Prompt Overrides

Leave prompt fields empty to use Shippy defaults. Set a field to replace that
prompt completely.

Use `[extra_instructions]` when you want to keep the default prompt and append
local rules.

`split_group` means: **prompt for one chunk of changed files**.

Shippy flow:

1. Split changed files into focused groups.
2. Run summary/review workers in parallel.
3. Merge worker output into one final PR body or sticky review comment.

Supported prompt tokens:

- `summary_split_group`: `{{area}}`, `{{branch}}`, `{{base}}`, `{{ignored_paths}}`, `{{files}}`, `{{diff}}`
- `summary_final`: `{{branch}}`, `{{base}}`, `{{commits}}`, `{{stat}}`, `{{area_summaries}}`, `{{title_prefixes}}`, `{{title_update}}`, `{{title_enforce_prefix}}`
- `review_split_group`: `{{area}}`, `{{pr_title}}`, `{{pr_url}}`, `{{pr_body}}`, `{{branch}}`, `{{base}}`, `{{commits}}`, `{{stat}}`, `{{files}}`, `{{diff}}`, `{{trim_note}}`
- `review_final`: `{{pr_title}}`, `{{pr_url}}`, `{{pr_body}}`, `{{branch}}`, `{{base}}`, `{{commits}}`, `{{stat}}`, `{{changed_files}}`, `{{diff}}`, `{{area_reviews}}`, `{{trim_note}}`

---

## 🧪 Run

Run it from anywhere inside a Git work tree. Shippy discovers the repository
root automatically.

```sh
shippy summary
shippy review
```

With an explicit PR URL or custom config:

```sh
shippy --pr-url "$PR_URL" summary
shippy --config ./custom.toml --pr-url "$PR_URL" review
```

From a local checkout:

```sh
uv run -m shippy.cli summary
uv run -m shippy.cli review
```

Useful commands:

```sh
shippy init
shippy --help
shippy --version
shippy summary --help
shippy review --help
```

---

## 🧾 Example Review Output

```md
## AI Review

### Verdict
✅ Pass: no blocking issue visible.

### Summary
- Adds PR review through the configured AI platform.
- Splits changed files into focused review groups.
- Publishes one sticky Markdown comment on GitHub.

### Findings
- No blocking issues found in the visible diff.

### Tests
- Unit tests were not visible in PR context.

### Reviewer Notes
- Diff was complete.
```

---

## 🔒 Privacy

Current Ollama + GitHub support talks to:

- your local Git repository
- GitHub through `gh`
- your configured Ollama server

Your prompt is sent to the AI platform endpoint you configure.

---

## 🧰 Development

For contributors cloning this repo, use the root Taskfile as the entrypoint:

```sh
task prereq
task format
task check
task publish:check
```

---

## 🤝 Contributing

PRs are welcome.

Especially useful contributions:

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

## 📄 License

MIT
