# docker-picamera

> <TBD>

<one paragraph: what it does, for whom, and its fleet role — producer, consumer or leaf — naming the siblings it depends on or serves>

## Install

    <the one install line for python — e.g. `uv sync` · `go mod download` · nothing for bash>

## Run

    <the one run line — e.g. `uv run docker-picamera --help` · `./bin/docker-picamera --help` · `make run`>

Every verb also has a skill — `CLAUDE.md` § 3 lists them.

## Configuration

| variable | what it points at | required |
| --- | --- | --- |
| `<PROJECT>_<TIER>_DIR` | <what lives there, who owns it, what it costs to rebuild> | yes |

## Development

    <test · lint · type-check, one line each — e.g. `uv run pytest` · `uv run ruff check .` · `uv run mypy src`>
    pre-commit run --all-files

## Secrets

macOS Keychain, service `{{KEYCHAIN_SERVICE}}`. Required keys: [`.env.example`](.env.example).
Populate with `bin/set-secret.sh <KEY>` (one key) or `bin/set-secret.sh --bootstrap` (every key);
load with `source bin/load-secrets.sh`. Never commit a `.env`.

## Documentation

- [`architecture.md`](architecture.md) — how the code is organised; read it before changing it
- [`CLAUDE.md`](CLAUDE.md) — what a Claude session reads at start; a router, not a manual
- `openspec/` — `specs/` is what it must do; `ideas.md` § Archived is what shipped and why
