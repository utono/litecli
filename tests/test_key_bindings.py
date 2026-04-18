from __future__ import annotations

from unittest.mock import MagicMock

from prompt_toolkit.filters import Always
from prompt_toolkit.keys import Keys

from litecli.key_bindings import cli_bindings


def _find_tab_bindings(kb):
    """Return (filtered_binding, unfiltered_binding) for the Tab key."""
    tab_bindings = [b for b in kb.bindings if b.keys == (Keys.ControlI,)]
    filtered = [b for b in tab_bindings if not isinstance(b.filter, Always)]
    unfiltered = [b for b in tab_bindings if isinstance(b.filter, Always)]
    assert len(filtered) == 1, f"expected exactly one filtered Tab binding, got {len(filtered)}"
    assert len(unfiltered) == 1, f"expected exactly one unfiltered Tab binding, got {len(unfiltered)}"
    return filtered[0], unfiltered[0]


def test_tab_with_selection_clears_complete_state_and_inserts_space():
    """Tab accepts the highlighted completion and appends a trailing space."""
    kb = cli_bindings(MagicMock())
    filtered, _ = _find_tab_bindings(kb)

    event = MagicMock()
    buffer = event.app.current_buffer
    buffer.complete_state = MagicMock()  # simulate "menu open with selection"

    filtered.handler(event)

    assert buffer.complete_state is None
    buffer.insert_text.assert_called_once_with(" ")


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
