# Contributing

## Development

```sh
python -m pip install -e ".[dev]"
python -m unittest discover -s tests
python -m build
```

## Standards

- Keep runtime dependencies small and justified.
- Keep generated PR comments Markdown-only.
- Keep failures explicit and user-actionable.
- Do not add hosted AI defaults.
- Do not log secrets, tokens, prompts with private code, or full GitHub responses.

## Pull Requests

- Add or update tests for behavior changes.
- Update `README.md` for user-facing changes.
- Update `CHANGELOG.md` for release-worthy changes.
- Keep the public CLI stable unless the version is bumped accordingly.
