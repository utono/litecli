# Cap `\f` completions by saved query placeholder count — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After `\f <name>`, cap table/view suggestions by the number of positional placeholders (`?` and distinct `$N`) in the saved favorite query, so placeholder-less favorites show no menu and fully-filled favorites stop suggesting.

**Architecture:** Add a small `_count_placeholders` helper and modify the `\f` branch of `suggest_special` in `litecli/packages/completion_engine.py`. Look up the saved query via the existing `iocommands.favoritequeries` module-global (already imported by `sqlcompleter.py`), compute `arg_index - 1 > placeholder_count`, and return `[]` when exhausted. Unknown names fall back to today's table/view suggestion.

**Tech Stack:** Python 3.10+, `re` (stdlib regex), pytest + `monkeypatch`.

**Spec:** `docs/superpowers/specs/2026-04-18-favorite-query-arg-cap-design.md`

---

## File Structure

- **Modify:** `litecli/packages/completion_engine.py` — add `import re` at the top; add `_count_placeholders(query: str) -> int` helper near `_expecting_arg_idx` (around line 136); replace the `\f` branch of `suggest_special` (lines 107-111). Net ~20 new lines.
- **Modify:** `tests/test_dbspecial.py` — add four tests that use `monkeypatch` on `litecli.packages.special.iocommands.favoritequeries.get` to exercise the new capping logic. Net ~50 new lines.
- **Modify:** `CHANGELOG.md` — add a `### Bug Fixes` bullet under the existing `Unreleased` section.

---

## Task 1: Write failing tests for the four capping cases

**Files:**
- Modify: `tests/test_dbspecial.py`

- [ ] **Step 1: Append the four new tests to `tests/test_dbspecial.py`**

The file currently ends with `test_special_d_w_arg` at line 104. Append the following after it (keep a blank line between the existing last test and the new section):

```python


# --- Tests for `\f <name>` argument-count capping (see Task plan). ---
# These stub iocommands.favoritequeries.get so the tests don't touch the user's
# real ~/.config/litecli/config.


def _stub_favorite(monkeypatch, query):
    """Replace favoritequeries.get so it returns `query` for any name."""
    from litecli.packages.special import iocommands

    monkeypatch.setattr(iocommands.favoritequeries, "get", lambda _name: query)


def test_favorite_query_no_placeholders_returns_empty(monkeypatch):
    """`\\f name ` with a placeholder-less saved query yields no suggestions."""
    _stub_favorite(monkeypatch, "SELECT 1")
    assert suggest_type("\\f name ", "\\f name ") == []


def test_favorite_query_within_placeholder_count_suggests_tables(monkeypatch):
    """`\\f name ` with a 1-placeholder saved query still suggests tables/views."""
    _stub_favorite(monkeypatch, "SELECT * FROM t WHERE id = ?")
    suggestions = suggest_type("\\f name ", "\\f name ")
    assert sorted_dicts(suggestions) == sorted_dicts(
        [
            {"type": "table", "schema": []},
            {"type": "view", "schema": []},
        ]
    )


def test_favorite_query_exceeded_placeholder_count_returns_empty(monkeypatch):
    """After the placeholder is filled, no further suggestions."""
    _stub_favorite(monkeypatch, "SELECT * FROM t WHERE id = ?")
    assert suggest_type("\\f name 42 ", "\\f name 42 ") == []


def test_favorite_query_unknown_name_falls_back_to_tables(monkeypatch):
    """Unknown favorite name preserves table/view suggestions (typo recovery)."""
    from litecli.packages.special import iocommands

    monkeypatch.setattr(iocommands.favoritequeries, "get", lambda _name: None)
    suggestions = suggest_type("\\f nopesuch ", "\\f nopesuch ")
    assert sorted_dicts(suggestions) == sorted_dicts(
        [
            {"type": "table", "schema": []},
            {"type": "view", "schema": []},
        ]
    )
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/test_dbspecial.py -v -k favorite_query`

Expected: all four tests FAIL. The specific failures:

- `test_favorite_query_no_placeholders_returns_empty` — assertion fails because `suggest_type` returns the table/view list unconditionally today (`[{"type": "table", "schema": []}, {"type": "view", "schema": []}]`), not `[]`.
- `test_favorite_query_within_placeholder_count_suggests_tables` — this one may PASS today because the current code returns exactly the list being asserted. That's fine — it's a regression-protection test for Task 2's implementation.
- `test_favorite_query_exceeded_placeholder_count_returns_empty` — fails for the same reason as test 1 (returns tables instead of `[]`).
- `test_favorite_query_unknown_name_falls_back_to_tables` — this also passes today (current code doesn't look up the name at all). Also regression-protection.

At least two of the four tests MUST fail in red phase. If all four pass, something is wrong (either your code already does the capping, or the stub isn't effective). Investigate before proceeding.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/test_dbspecial.py
git commit -m "test: add failing tests for \\f placeholder-count capping"
```

---

## Task 2: Implement `_count_placeholders` and update the `\f` branch

**Files:**
- Modify: `litecli/packages/completion_engine.py`

- [ ] **Step 1: Add `import re` at the top of the module**

Edit `litecli/packages/completion_engine.py`. Current lines 1-8 look like:

```python
from __future__ import annotations

from typing import Any

import sqlparse
from sqlparse.sql import Comparison, Identifier, Where, Token
from .parseutils import last_word, extract_tables, find_prev_keyword
from .special.main import parse_special_command
```

Change to add `import re` (in the stdlib block alphabetically between `from __future__` and `from typing`):

```python
from __future__ import annotations

import re
from typing import Any

import sqlparse
from sqlparse.sql import Comparison, Identifier, Where, Token
from .parseutils import last_word, extract_tables, find_prev_keyword
from .special.main import parse_special_command
```

- [ ] **Step 2: Add the `_count_placeholders` helper**

Locate the existing `_expecting_arg_idx` helper (around line 136). Immediately ABOVE it, insert:

```python
def _count_placeholders(query: str) -> int:
    """Count positional placeholders in a favorite query.

    Mirrors iocommands.subst_favorite_query_args:
    - Each `?` is a separate placeholder (left-to-right substitution).
    - Each distinct `$N` counts once (all occurrences of the same `$N`
      receive the same value).

    Returns the number of arguments a user can meaningfully supply.
    """
    dollar_args = set(re.findall(r"\$\d+", query))
    question_args = query.count("?")
    return len(dollar_args) + question_args


```

(Note the trailing blank line before `_expecting_arg_idx` — maintains the existing one-blank-line spacing between module-level defs.)

- [ ] **Step 3: Replace the `\f` branch of `suggest_special`**

Currently at `litecli/packages/completion_engine.py:107-111`:

```python
    if cmd == "\\f":
        if _expecting_arg_idx(arg, text) == 1:
            return [{"type": "favoritequery"}]
        else:
            return [{"type": "table", "schema": []}, {"type": "view", "schema": []}]
```

Replace with:

```python
    if cmd == "\\f":
        if _expecting_arg_idx(arg, text) == 1:
            return [{"type": "favoritequery"}]

        # Arg 2+: cap table/view suggestions by the saved query's placeholder count.
        from .special.iocommands import favoritequeries

        name = arg.split()[0] if arg.strip() else ""
        query = favoritequeries.get(name) if name else None
        if query is None:
            # Unknown favorite name — keep table/view suggestion so a mid-typing
            # typo doesn't silently kill the menu.
            return [{"type": "table", "schema": []}, {"type": "view", "schema": []}]
        if _expecting_arg_idx(arg, text) - 1 > _count_placeholders(query):
            return []
        return [{"type": "table", "schema": []}, {"type": "view", "schema": []}]
```

Rationale for the late-binding `from .special.iocommands import favoritequeries` inside the branch (rather than at the top of the module): matches the existing pattern in `sqlcompleter.py` and avoids the import-capture bug documented in `tests/test_smart_completion_public_schema_only.py:375` — the module global may be reassigned at runtime when `FavoriteQueries.from_config()` is called.

- [ ] **Step 4: Run the four favorite-query tests**

Run: `pytest tests/test_dbspecial.py -v -k favorite_query`

Expected: all four PASS.

- [ ] **Step 5: Run the full test suite**

Run: `pytest -q`

Expected: same count as before plus the four new ones, all green.

- [ ] **Step 6: Run the style check**

Run: `ruff check litecli/packages/completion_engine.py tests/test_dbspecial.py && ruff format --check litecli/packages/completion_engine.py tests/test_dbspecial.py`

Expected: no errors, no reformatting needed.

- [ ] **Step 7: Commit the implementation**

```bash
git add litecli/packages/completion_engine.py
git commit -m "fix(\\f): cap completions by saved query placeholder count

After \\f <name>, count positional placeholders (? and distinct \$N) in
the saved query and suppress further table/view suggestions once
exhausted. Placeholder-less favorites show no menu at all. Unknown
names still get table/view suggestions so mid-typing typos don't kill
the completer.

Fixes the case where Tab after a placeholder-less favorite led users
into \"Too many arguments\" at run time."
```

---

## Task 3: Changelog entry

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add a Bug Fixes bullet under Unreleased**

The current Unreleased section reads:

```markdown
## Unreleased

### Features

- `Tab` now accepts the highlighted completion and inserts a trailing space when the completion menu is open. Use `Ctrl+N`/`Ctrl+P` or `Shift+Tab` to cycle through suggestions.

### Internal

- Add a GitHub Actions workflow to run Codex review on pull requests.
- Drop Python 3.9 from test matrices and tooling targets.
```

Add a new `### Bug Fixes` subsection between `### Features` and `### Internal`:

```markdown
## Unreleased

### Features

- `Tab` now accepts the highlighted completion and inserts a trailing space when the completion menu is open. Use `Ctrl+N`/`Ctrl+P` or `Shift+Tab` to cycle through suggestions.

### Bug Fixes

- `\f <name>` stops suggesting completions once the saved query's positional placeholders (`?` and `$N`) are exhausted. Favorites with no placeholders no longer open a suggestion menu after the name.

### Internal

- Add a GitHub Actions workflow to run Codex review on pull requests.
- Drop Python 3.9 from test matrices and tooling targets.
```

- [ ] **Step 2: Commit the changelog entry**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog entry for \\f placeholder-count capping"
```

---

## Task 4: Manual smoke test

**Files:** (none; exercises the live REPL)

- [ ] **Step 1: Reinstall via pipx so `lc` reflects the new commits**

From a directory that is NOT the source tree (pipx rejects `.` when you run it from the source dir):

```bash
cd /tmp && pipx install --force --editable /home/mlj/utono/litecli
litecli -V
```

Expected: version string contains the new commit SHA (not the previous `g24381a153`).

- [ ] **Step 2: Verify placeholder-less favorite suppresses menu**

Run `lc`. At the prompt, type:

```
\f schema_gloss_devices 
```

(note the trailing space). Expected: NO completion menu opens. If you press Tab, nothing happens (no cycling through tables).

- [ ] **Step 3: Verify a favorite with placeholders still suggests tables**

Pick any saved favorite that contains a `?` or `$1`. For example, if you have one named `byid` with `SELECT * FROM ?  WHERE id = ?`, type:

```
\f byid 
```

Expected: table/view suggestion menu opens (same as before this change).

- [ ] **Step 4: Verify exhausted placeholders suppress menu**

Using the same favorite from Step 3 (assume it has 2 placeholders), type:

```
\f byid users 42 
```

Expected: no menu opens (both placeholders filled).

- [ ] **Step 5: Verify unknown name still suggests tables**

Type:

```
\f nopesuch 
```

Expected: table/view menu opens. This is the typo-recovery fallback — intentional.

- [ ] **Step 6: Exit litecli**

Type `\q` or press Ctrl+D.
