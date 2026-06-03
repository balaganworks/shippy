# Release

1. Update `version` in `pyproject.toml`.
2. Update `CHANGELOG.md`.
3. Open a PR and wait for CI.
4. Tag and push:

```sh
git tag v0.1.0
git push origin v0.1.0
```

5. Create a GitHub release from the tag.
6. GitHub Actions publishes to PyPI through trusted publishing.

Before first release, configure PyPI trusted publishing for:

- repository: `balaganworks/shippy`
- workflow: `publish.yml`
- environment: optional
