# Contributing to Argus

Thanks for your interest! Argus is primarily a personal project, but it's run with the
discipline of a collaborative one so that other people — and coding agents — can work
in it cleanly.

## Ground rules

- **Land changes via pull request**, not direct pushes to `main`. `main` is protected.
- **Sign your commits** (`git commit -S`). Verified signatures are required.
- **Update [CHANGELOG.md](CHANGELOG.md)** under `## [Unreleased]` for any user-visible change.
- **Capture decisions as ADRs.** Anything architectural goes in
  [`docs/architecture/adr/`](docs/architecture/adr/) — copy the format from an existing one
  and add it to the index.
- **Track work in issues.** Use the bug / feature templates.

## Development setup

### Server (`server/`)

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

ruff check src tests        # lint (must pass CI)
mypy src                    # type check
pytest -v                   # tests (offline — NetBox is mocked)
```

### Web (`web/`)

```bash
cd web
npm install
npm run lint
npx tsc --noEmit
npm run build
```

## Pull request process

1. Branch off `main`: `git checkout -b feature/your-change`.
2. Make focused commits with clear, conventional messages (`feat:`, `fix:`, `docs:`,
   `chore:`, `deps:`, `ci:`).
3. Add or update tests and docs as needed.
4. Update `CHANGELOG.md`.
5. Open a PR; ensure the `server` and `web` CI checks pass.
6. Squash-merge once green (the repo is squash-only).

## Code style

- **Python**: 3.12+, line length 100, Ruff (`E, F, I, UP, B, SIM`), typed where practical.
- **TypeScript/React**: ESLint flat config, strict TypeScript, function components + hooks.

## Reporting issues

Use the issue templates and include enough detail to reproduce. For security issues,
see [SECURITY.md](SECURITY.md) — do not open a public issue.
