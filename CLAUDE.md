# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`litecli` is a command-line SQLite client (dbcli family) with autocompletion and syntax highlighting. Console entry point `litecli = litecli.main:cli` (see `pyproject.toml`). Python 3.10+.

Extensive repository conventions — formatter settings, test commands, commit style, changelog discipline — are documented in `AGENTS.md`. Read it before non-trivial changes.

**Upstream:** Forked from [`dbcli/litecli`](https://github.com/dbcli/litecli). The upstream remote is preconfigured as `upstream`; `origin` points to `utono/litecli`.

**Arch Linux package:** Available on the AUR as `litecli` (release) and `litecli-git` (VCS build). Install with `paru -S litecli`.

**Running your local fork instead of the AUR package (Arch):** This machine installs `litecli` via `pipx` from the local source tree so the `litecli`/`lc` command reflects your working-tree commits. `setuptools-scm` derives the version from git, so `litecli -V` shows `1.17.x.devN+g<sha>` and the `.d<YYYYMMDD>` suffix appears when the working tree is dirty.

```bash
# First-time install (or after a pip cache wipe):
cd /home/mlj/utono/litecli
pipx install --force --editable .

# After making code changes, reinstall to pick up the new git SHA in the version
# string. pipx resolves "." against $PWD, so run this from *outside* the repo or
# it fails with "looks like a path. Expected the name of an installed package":
cd /tmp && pipx install --force --editable /home/mlj/utono/litecli

# Verify:
litecli -V
# → litecli, version 1.17.x.devN+g<sha>.d<YYYYMMDD>
```

If the AUR `litecli` is also installed, pipx's shim in `~/.local/bin/litecli` takes precedence on this system's `$PATH`. Uninstall the AUR package with `paru -R litecli` if you want a single source of truth. To roll back to the AUR build: `pipx uninstall litecli && paru -S litecli`.

## Commands

Setup:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Tests:
```bash
tox                       # full matrix + coverage (py, style, sqlean)
tox -e sqlean             # with the sqlean-py extension backend
pytest -q                 # fast direct run
pytest -k <keyword>       # focused
pytest tests/test_main.py::test_name   # single test
```

Lint / format / type-check:
```bash
tox -e style              # ruff check --fix + ruff format (canonical style pass)
ruff check --fix
ruff format
ty check -v               # repo-wide type check (configured in pyproject.toml)
ty check litecli -v       # per-package
```

Run the CLI from source: `litecli path/to.db`.

Note: some CLI tests expect `ex` to be a symlink to `vim` (not `vi`). Check with `readlink -f $(which ex)` if tests unexpectedly fail.

## Architecture

The runtime splits into three layers: the interactive shell (prompt_toolkit wiring), the SQL execution layer (sqlite3/sqlean wrapper), and a special-command subsystem that provides backslash commands and completion metadata.

**Shell layer — `litecli/main.py`**
The `LiteCli` class (~40kb, the biggest file in the repo) owns the REPL. It constructs the prompt_toolkit `PromptSession`, wires the lexer (`lexer.py`), style (`clistyle.py`), toolbar (`clitoolbar.py`), key bindings (`key_bindings.py`), and multiline buffer detection (`clibuffer.py`). It dispatches each input either to the special-command executor or to `SQLExecute`.

**SQLite backend detection — `main.py` + `sqlexecute.py`**
Both modules try `import sqlean` first and fall back to stdlib `sqlite3`. `sqlean-py` is the optional extension-enabled backend (installed via the `[sqlean]` extra); when present, `sqlean.extensions.enable_all()` is called. Code that touches the connection must work against either. `SQLExecute` issues `PRAGMA database_list` / `sqlite_master` queries to feed the completer.

**Special commands — `litecli/packages/special/`**
`main.py` defines the `@special_command(...)` decorator and a global `COMMANDS` registry. Command handlers live in:
- `dbcommands.py` — `.tables`, `.schema`, `.databases`, etc.
- `iocommands.py` — `\e` editor, `tee`, pager, favorite queries, output redirection.
- `llm.py` — `\llm`/`\ai` integration, gated on the optional `llm` package (ai extra).
- `favoritequeries.py` — persisted named queries.

`arg_type` on each command controls how the input is parsed: `NO_QUERY` (no args), `PARSED_QUERY` (receives `cur`, `arg`, `verbose`), or `RAW_QUERY` (receives the full SQL). Verbosity is signalled by `+`/`-` suffixes on the command (`parse_special_command` in `main.py`). The `@export` decorator in `special/__init__.py` controls the public re-export surface.

**Completion — `litecli/sqlcompleter.py` + `litecli/packages/completion_engine.py`**
`completion_engine.py` parses the partial input (using `parseutils.py` on top of `sqlparse`) to decide what kind of suggestion applies at the cursor (keyword, table, column, favorite-query name, etc.). `sqlcompleter.py` holds the in-memory schema cache populated from `SQLExecute`, and turns suggestions into prompt_toolkit `Completion` objects. `completion_refresher.py` re-runs the metadata queries on a background thread after schema-changing statements.

**Config — `litecli/config.py` + `litecli/liteclirc`**
`liteclirc` is the template shipped inside the package (see `[tool.setuptools.package-data]`) and copied to `~/.config/litecli/config` on first launch (or `%LOCALAPPDATA%/dbcli/litecli/config` on Windows). `config.py` resolves location and loads via `configobj`. Tests override the config home via `XDG_CONFIG_HOME` in `tests/conftest.py` — never read user config directly.

## Conventions worth repeating

- Line length 140; ruff is the single source of truth for style (`.pre-commit-config.yaml` + `tox -e style`).
- Type hints: lowercase generics (`list`, `dict`, `tuple`), `|` for unions, `| None` for optional.
- Tests live in `tests/test_<unit>.py`; use fixtures from `tests/conftest.py` (it manages a temporary `_test_db` and an isolated config home).
- User-visible changes need a `CHANGELOG.md` entry under an `Unreleased` section (Features / Bug Fixes / Internal).
- Don't commit local SQLite files or secrets — fixtures go in `tests/data/`.

## Memory Bank System

This project uses a structured memory bank system. Always check these context
files before starting work, and keep them updated as the project evolves:

- **CLAUDE-activeContext.md** — current session state, goals, and progress
- **CLAUDE-patterns.md** — established code patterns and conventions
- **CLAUDE-decisions.md** — architecture decisions and rationale
- **CLAUDE-troubleshooting.md** — common issues and proven solutions
- **CLAUDE-config-variables.md** — configuration variables reference

Always read **CLAUDE-activeContext.md** first to maintain session continuity.
When you change core context, update the relevant memory bank file.
