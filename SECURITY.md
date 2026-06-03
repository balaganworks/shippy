# Security Policy

## Supported Versions

Only the latest released version receives security fixes.

## Reporting a Vulnerability

Open a private security advisory on GitHub, or email the maintainer listed in
the extracted repository.

Please include:

- affected version
- reproduction steps
- impact
- suggested fix, if known

## Scope

`shippy` shells out to `git`, `gh`, and `ollama`.

Do not run it on untrusted repositories unless you already trust the local
tooling and Git hooks in that checkout.
