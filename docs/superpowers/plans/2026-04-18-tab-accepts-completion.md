# Tab accepts highlighted completion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Tab` accept the currently highlighted completion when litecli's completion menu is open with a selection, while preserving its existing "open the menu" behavior when no menu is showing.

**Architecture:** Add a second Tab key binding in `litecli/key_bindings.py` guarded by prompt_toolkit's `completion_is_selected` filter. prompt_toolkit's key processor prefers the filtered binding over the unfiltered one when the filter matches, so the new handler fires only when a completion is highlighted and clears `complete_state` (the same pattern used for `Right` and `Enter` today). No other keys change.

**Tech Stack:** Python 3.10+, `prompt_toolkit` (`KeyBindings`, `completion_is_selected` filter), pytest + `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-04-18-tab-accepts-completion-design.md`

---

## File Structure

- **Modify:** `litecli/key_bindings.py` — add one `@kb.add("tab", filter=completion_is_selected)` handler above the existing unfiltered Tab handler (line 34). ~7 new lines.
- **Create:** `tests/test_key_bindings.py` — two unit tests. Uses `unittest.mock.MagicMock` only; no live `PromptSession` needed.
- **Modify:** `CHANGELOG.md` — add a bullet under the existing `Unreleased` → new `Features` subsection.

---

## Task 1: Write the failing test for the new Tab-accepts handler

**Files:**
- Create: `tests/test_key_bindings.py`

- [ ] **Step 1: Create the test file with the two tests**

```python
# tests/test_key_bindings.py
from __future__ import annotations

from unittest.mock import MagicMock

from prompt_toolkit.keys import Keys

from litecli.key_bindings import cli_bindings


def _find_tab_bindings(kb):
    """Return (filtered_binding, unfiltered_binding) for the Tab key."""
    tab_bindings = [b for b in kb.bindings if b.keys == (Keys.ControlI,)]
    filtered = [b for b in tab_bindings if repr(b.filter) != "Always()"]
    unfiltered = [b for b in tab_bindings if repr(b.filter) == "Always()"]
    assert len(filtered) == 1, f"expected exactly one filtered Tab binding, got {len(filtered)}"
    assert len(unfiltered) == 1, f"expected exactly one unfiltered Tab binding, got {len(unfiltered)}"
    return filtered[0], unfiltered[0]


def test_tab_with_selection_clears_complete_state():
    """Tab accepts the highlighted completion by clearing complete_state."""
    kb = cli_bindings(MagicMock())
    filtered, _ = _find_tab_bindings(kb)

    event = MagicMock()
    buffer = event.app.current_buffer
    buffer.complete_state = MagicMock()  # simulate "menu open with selection"

    filtered.handler(event)

    assert buffer.complete_state is None


def test_tab_with_no_selection_starts_completion():
    """Tab opens the completion menu with the first item selected when no menu is open."""
    kb = cli_bindings(MagicMock())
    _, unfiltered = _find_tab_bindings(kb)

    event = MagicMock()
    buffer = event.app.current_buffer
    buffer.complete_state = None

    unfiltered.handler(event)

    buffer.start_completion.assert_called_once_with(select_first=True)
    buffer.complete_next.assert_not_called()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_key_bindings.py -v`
Expected: `test_tab_with_selection_clears_complete_state` FAILS with an `AssertionError` from `_find_tab_bindings` — "expected exactly one filtered Tab binding, got 0".
`test_tab_with_no_selection_starts_completion` may also fail for the same reason (the helper asserts *both* bindings exist).

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_key_bindings.py
git commit -m "test: add failing tests for Tab-accepts-completion key binding"
```

---

## Task 2: Add the Tab-accepts handler

**Files:**
- Modify: `litecli/key_bindings.py:33-42` (insert new handler immediately above the existing `@kb.add("tab")` block at line 34)

- [ ] **Step 1: Insert the new filtered Tab handler**

Edit `litecli/key_bindings.py`. Locate the existing unfiltered Tab handler:

```python
    @kb.add("tab")
    def _(event: KeyPressEvent) -> None:
        """Force autocompletion at cursor."""
        _logger.debug("Detected <Tab> key.")
        b = event.app.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            b.start_completion(select_first=True)
```

Insert the new filtered handler directly **above** it, so the filtered handler is registered first (prompt_toolkit tries bindings in registration order and prefers the one whose filter matches):

```python
    @kb.add("tab", filter=completion_is_selected)
    def _(event: KeyPressEvent) -> None:
        """Accept the highlighted completion (Tab)."""
        _logger.debug("Detected <Tab> key with completion selected.")
        b = event.app.current_buffer
        b.complete_state = None

    @kb.add("tab")
    def _(event: KeyPressEvent) -> None:
        """Force autocompletion at cursor."""
        _logger.debug("Detected <Tab> key.")
        b = event.app.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            b.start_completion(select_first=True)
```

Also simplify the unfiltered handler by removing the now-dead `if b.complete_state: b.complete_next()` branch — with the filtered handler intercepting the "menu open with selection" case, the only state the unfiltered handler can see is `complete_state is None` (menu closed) or menu open without selection (`complete_next` is still the right behavior for the latter, so keep the branch as-is to avoid changing cycling behavior when the user arrived at "no selection" via Ctrl+Space).

**Decision:** keep the existing `if b.complete_state` branch untouched. It preserves Ctrl+Space-then-Tab cycling. Only the highlighted-selection case is diverted.

Final state of lines 33-51 in `litecli/key_bindings.py`:

```python
    @kb.add("tab", filter=completion_is_selected)
    def _(event: KeyPressEvent) -> None:
        """Accept the highlighted completion (Tab)."""
        _logger.debug("Detected <Tab> key with completion selected.")
        b = event.app.current_buffer
        b.complete_state = None

    @kb.add("tab")
    def _(event: KeyPressEvent) -> None:
        """Force autocompletion at cursor."""
        _logger.debug("Detected <Tab> key.")
        b = event.app.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            b.start_completion(select_first=True)
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `pytest tests/test_key_bindings.py -v`
Expected: both tests PASS.

- [ ] **Step 3: Run the full test suite to check for regressions**

Run: `pytest -q`
Expected: all tests pass (same count as before plus the two new ones).

- [ ] **Step 4: Run the style check**

Run: `tox -e style`
Expected: ruff reports no errors, no files reformatted.

- [ ] **Step 5: Commit the implementation**

```bash
git add litecli/key_bindings.py
git commit -m "feat(keys): bind Tab to accept highlighted completion

When the completion menu is open with an item highlighted, pressing Tab
now accepts the selection (matching Right/Enter). Tab still opens the
menu when none is showing. Use Ctrl+N/Ctrl+P or Shift+Tab to cycle."
```

---

## Task 3: Update the changelog

**Files:**
- Modify: `CHANGELOG.md:1-6`

- [ ] **Step 1: Add a Features subsection under Unreleased**

Edit `CHANGELOG.md`. Change:

```markdown
## Unreleased

### Internal

- Add a GitHub Actions workflow to run Codex review on pull requests.
- Drop Python 3.9 from test matrices and tooling targets.
```

To:

```markdown
## Unreleased

### Features

- `Tab` now accepts the highlighted completion when the completion menu is open. Use `Ctrl+N`/`Ctrl+P` or `Shift+Tab` to cycle through suggestions.

### Internal

- Add a GitHub Actions workflow to run Codex review on pull requests.
- Drop Python 3.9 from test matrices and tooling targets.
```

- [ ] **Step 2: Commit the changelog entry**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog entry for Tab-accepts-completion"
```

---

## Task 4: Manual smoke test

**Files:** (none; exercises the live REPL)

- [ ] **Step 1: Launch litecli against the test database**

Run: `litecli tests/data/doesnt_exist.db` (or any convenient SQLite file)

- [ ] **Step 2: Verify Tab accepts a highlighted completion**

At the prompt, type `SEL` then press `Tab`. Expected: the menu opens with `SELECT` highlighted (first item selected per existing behavior). Press `Tab` a second time. Expected: `SELECT` is inserted and the menu closes.

- [ ] **Step 3: Verify Ctrl+N / Ctrl+P still cycle**

Type `S` then `Tab`. Menu opens with first suggestion highlighted. Press `Ctrl+N`. Expected: next suggestion highlights. Press `Ctrl+P`. Expected: previous suggestion highlights. Press `Tab`. Expected: currently highlighted suggestion accepted.

- [ ] **Step 4: Verify Shift+Tab still cycles backward**

Type `S` then `Tab`. Press `Shift+Tab`. Expected: selection moves to the previous suggestion. Press `Tab`. Expected: highlighted suggestion accepted.

- [ ] **Step 5: Verify Ctrl+Space still opens without preselection**

At a clean prompt, press `Ctrl+Space`. Expected: menu opens with no item highlighted. Press `Tab`. Expected: first item becomes highlighted (unfiltered handler's `complete_next` branch fires). Press `Tab` again. Expected: highlighted item accepted.

- [ ] **Step 6: Exit litecli**

Type `\q` or press `Ctrl+D`.
