# Tab accepts highlighted completion

**Date:** 2026-04-18
**Status:** Approved, ready for implementation plan

## Problem

In litecli's REPL, when the completion menu is open with an item highlighted, pressing `Tab` advances to the next item. Users who expect Tab to *accept* the current highlight (the behavior of `Right` and `Enter` in litecli today, and of Tab in most shells and editors) must instead press Right, Enter, or `Ctrl+F` (which happens to work only as a side effect of prompt_toolkit's default emacs `forward-char` binding being equivalent to `Right`).

The user cycles completions with `Ctrl+N` / `Ctrl+P` (prompt_toolkit emacs defaults) and wants Tab dedicated to accepting.

## Goal

Make Tab accept the currently highlighted completion when the completion menu is open with a selection. Preserve Tab's existing behavior when no menu is open (open the menu with the first item selected).

## Non-goals

- Changing `Shift+Tab`, `Ctrl+Space`, `Ctrl+N`, `Ctrl+P`, `Right`, or `Enter` behavior.
- Exposing keybindings as user configuration.
- Altering completion logic itself (what gets suggested, in what order).

## Design

Add one new key binding in `litecli/key_bindings.py` inside `cli_bindings()`:

```python
@kb.add("tab", filter=completion_is_selected)
def _(event: KeyPressEvent) -> None:
    """Accept the highlighted completion (Tab)."""
    _logger.debug("Detected Tab key with completion selected.")
    b = event.app.current_buffer
    b.complete_state = None
```

This mirrors the existing `Right` handler at lines 87-93 and the `Enter` handler at lines 72-85. prompt_toolkit's key processor prefers a binding with a matching filter over an unfiltered one for the same key, so when the completion menu has a highlighted item, this handler wins over the existing unfiltered `@kb.add("tab")` block. When no item is selected (or no menu is open), the existing unfiltered handler continues to run and starts completion with `select_first=True`.

### Resulting behavior matrix

| State                                         | Tab            | Shift+Tab      | Ctrl+Space     | Right / Enter  |
| --------------------------------------------- | -------------- | -------------- | -------------- | -------------- |
| No completion menu                            | open + select first | open + select last | open, no selection | (default)      |
| Menu open, no item selected                   | select next    | select previous | select next   | (default)      |
| Menu open, item highlighted (selected)        | **accept (new)** | select previous | select next   | accept         |

### Why filter-based dispatch, not rewriting the existing handler

Two key considerations:

1. **Consistency with the rest of the file.** `Right` and `Enter` both use the `completion_is_selected` filter to implement "accept selection." Using the same pattern for Tab keeps the three acceptance keys visually and structurally aligned.
2. **Minimal diff, minimal risk.** The existing unfiltered `@kb.add("tab")` handler continues to handle the "no selection yet" case exactly as today. Nothing changes for users who relied on Tab-to-open.

## Testing

`tests/` does not currently cover `key_bindings.py`. We'll add a new `tests/test_key_bindings.py` that:

1. Calls `cli_bindings(MagicMock())` to obtain the `KeyBindings` registry.
2. Locates the Tab binding whose filter is `completion_is_selected` (by iterating `kb.bindings` and checking `binding.keys == (Keys.ControlI,)` — Tab's prompt_toolkit key name — and `binding.filter is not None`).
3. Invokes its handler with a mocked `KeyPressEvent` whose `app.current_buffer` is a mock with `complete_state` set to a sentinel.
4. Asserts `complete_state is None` after the call.

A second test can assert the unfiltered Tab handler still calls `start_completion(select_first=True)` when the buffer has no `complete_state`, to pin the fall-through behavior.

No integration test against a live `PromptSession` is proposed — the unit-level contract (filtered handler clears state, unfiltered handler starts completion) is sufficient, and matches how the rest of litecli treats `key_bindings.py`.

## Files changed

- `litecli/key_bindings.py` — add one `@kb.add("tab", filter=completion_is_selected)` handler (≈7 lines including docstring).
- `tests/test_key_bindings.py` — new file, two tests.
- `CHANGELOG.md` — entry under `Unreleased` → `Features`: "Tab now accepts the highlighted completion when the completion menu is open. Use `Ctrl+N`/`Ctrl+P` or `Shift+Tab` to cycle."

## Risks and open questions

- **Muscle memory regression.** Users who currently press Tab to *cycle* through completions (rather than using `Ctrl+Space` or `Ctrl+N`) will find the first Tab opens the menu and the second Tab accepts the highlight instead of advancing. Documented in the CHANGELOG entry. No telemetry suggests this is a common pattern.
- **Vi editing mode.** The `completion_is_selected` filter is mode-agnostic; the new binding applies in both emacs and vi modes. This is consistent with the existing `Right` and `Enter` bindings.
