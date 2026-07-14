# Cap completions after `\f <name>` by the saved query's placeholder count

**Date:** 2026-04-18
**Status:** Approved, ready for implementation plan

## Problem

`litecli`'s `\f <name> <args...>` command substitutes positional arguments (`?` or `$N`) into a saved favorite query. Commit `94e9eb2` added table/view completion after `\f <name>`, but it does so unconditionally — regardless of whether the saved query actually has any placeholders. A user hitting Tab after a placeholder-less favorite sees a suggestion menu, types or accepts something, and then the command fails with:

```
Too many arguments.
Query does not have enough place holders to substitute.
```

The completer is leading users into an error state.

## Goal

After `\f <name> `, cap the number of subsequent table/view suggestions by the number of placeholders in the saved query. Specifically:

- 0 placeholders → no suggestion menu opens at all.
- N placeholders → table/view suggestions for the first N positional args, then nothing.
- Unknown favorite name → keep today's table/view suggestion (typo-recovery affordance; the command will fail anyway with a clear error).

## Non-goals

- Validating placeholder syntax inside the saved query itself.
- Changing what gets substituted (still `?` left-to-right, `$N` by name).
- Special-casing `schema_*` favorites or any naming convention — the rule is structural (count placeholders).
- Showing an informational "this favorite takes no arguments" overlay. When zero suggestions apply, the menu simply doesn't open, consistent with everywhere else in litecli.
- Supporting `:name` or `?N` forms. litecli's `subst_favorite_query_args` (in `iocommands.py`) supports only `?` and `$<digit>+`, and that is the source of truth.

## Design

### Placeholder counting

Add a helper to `litecli/packages/completion_engine.py`:

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

### `\f` branch of `suggest_special`

Replace the current two-line `\f` block (`completion_engine.py:107-111`) with:

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

`re` needs to be imported at the top of `completion_engine.py` (currently not imported).

### Module coupling

`litecli/sqlcompleter.py:531` already imports and reads `iocommands.favoritequeries` to pull favorite names. Repeating that pattern in `completion_engine.py` is consistent with current code. The alternate design — threading a resolver through `suggest_type` — was considered and rejected: it'd add parameters to an already-exported API for a single call site.

The import lives inside the `\f` branch (not at module top) to keep the import graph identical to what it is today for non-`\f` calls — avoiding a subtle test-import ordering issue called out in `tests/test_smart_completion_public_schema_only.py:375` (the "from .iocommands import favoritequeries captured" bug).

### Behavior matrix

| Saved query placeholders | Input (cursor after trailing space)           | Suggestions                    |
| ------------------------ | ---------------------------------------------- | ------------------------------ |
| 0                        | `\f schema_gloss_devices `                     | **[]** — menu doesn't open     |
| 1 (`?`)                  | `\f byid `                                     | tables + views                 |
| 1 (`?`)                  | `\f byid 42 `                                  | **[]**                         |
| 2 (`?` + `?`)            | `\f range `                                    | tables + views                 |
| 2 (`?` + `?`)            | `\f range 1 `                                  | tables + views                 |
| 2 (`?` + `?`)            | `\f range 1 100 `                              | **[]**                         |
| 2 (`$1` + `$2`)          | `\f by_name foo `                              | tables + views                 |
| 3 (`$1` used twice + `$2` + `?`) | `\f complex a `                        | tables + views                 |
| unknown name (`nopesuch`) | `\f nopesuch `                                | tables + views (typo recovery) |

## Testing

`\f`-related completion tests live in `tests/test_dbspecial.py` (confirmed by inspection). Add four pytest functions there:

1. **`test_favorite_query_no_placeholders_returns_empty`** — stub `favoritequeries.get` (via `monkeypatch` on the module) to return a query like `SELECT 1`. Assert `suggest_type("\\f name ", "\\f name ")` returns `[]`.
2. **`test_favorite_query_within_placeholder_count_suggests_tables`** — stub query `"SELECT * FROM t WHERE id = ?"`. Assert `suggest_type("\\f name ", "\\f name ")` returns the table/view suggestion list.
3. **`test_favorite_query_exceeded_placeholder_count_returns_empty`** — same stub as (2). Assert `suggest_type("\\f name 42 ", "\\f name 42 ")` returns `[]`.
4. **`test_favorite_query_unknown_name_falls_back_to_tables`** — stub `favoritequeries.get` to return `None`. Assert the table/view fallback is returned.

No integration tests against a live `PromptSession` — the contract is "given `text_before_cursor`, `suggest_type` returns this list," which is exactly what the pytest tests cover.

## Files changed

- `litecli/packages/completion_engine.py` — add `import re`, add `_count_placeholders` helper, modify the `\f` branch of `suggest_special`. ~15 net new lines.
- `tests/test_dbspecial.py` — add four tests using `monkeypatch` to stub `iocommands.favoritequeries.get`. ~40 net new lines.
- `CHANGELOG.md` — entry under `Unreleased` → `Bug Fixes`: "`\f <name>` now stops suggesting completions once the saved query's positional placeholders (`?` and `$N`) are exhausted."

## Risks and open questions

- **`arg.split()[0]` for the favorite name.** If the user types `\f schema_gloss_devic ` (partial name), we'll look up `schema_gloss_devic`, get `None`, and fall back to table/view. Acceptable — the menu still works during typing and the command will fail at run time with a clear message.
- **Monkeypatch vs. real config fixture.** The existing `\f` tests in `tests/test_dbspecial.py` currently stub nothing (they test the name-completion path which doesn't hit `favoritequeries.get`). The new tests need a stub because `iocommands.favoritequeries` is a module-global initialized from user config. Using `monkeypatch.setattr(favoritequeries, 'get', ...)` keeps the test hermetic and avoids touching the user's actual `~/.config/litecli/config`.
- **Placeholder counting semantics for mixed `$N` + `?`.** Covered in the helper docstring and matrix row "3 (`$1` used twice + `$2` + `?`)". The `subst_favorite_query_args` logic substitutes `$N` *before* `?` per argument, but the *total count* is what determines completion capping, and both schemes contribute.
