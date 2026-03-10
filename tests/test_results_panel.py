"""Tests for ResultsPanel scrollback and mode-switching logic.

The buffer management (_buffer, _utility_buffer, _last_command_offset,
_utility_mode) is pure Python state.  We mock query_one() so the tests run
without a live Textual event loop.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from trawler.widgets.results_panel import ResultsPanel


# ---------------------------------------------------------------------------
# Factory — a ResultsPanel with DOM mocked out
# ---------------------------------------------------------------------------

def _make_panel() -> ResultsPanel:
    """Return a ResultsPanel whose Textual DOM calls are stubbed."""
    p = object.__new__(ResultsPanel)
    # Replicate __init__ state without calling Widget.__init__
    p._buffer = []
    p._utility_buffer = []
    p._last_command_offset = 0
    p._utility_mode = False

    _results_log = MagicMock()
    _utility_log = MagicMock()

    def _query_one(selector, *args):
        if "#utility-log" in str(selector):
            return _utility_log
        return _results_log   # "#results-log" or bare RichLog

    p.query_one = _query_one
    p._results_log = _results_log
    p._utility_log = _utility_log
    return p


# ---------------------------------------------------------------------------
# mark_command_start / last_command_context
# ---------------------------------------------------------------------------

def test_mark_command_start_empty_buffer_no_separator():
    """First mark on empty buffer: no separator lines, offset stays 0."""
    p = _make_panel()
    p.mark_command_start()
    assert p._buffer == []
    assert p._last_command_offset == 0


def test_mark_command_start_nonempty_buffer_adds_blank_lines():
    """Subsequent mark inserts two blank separator lines into the buffer."""
    p = _make_panel()
    p.write("result")
    p.mark_command_start()
    assert p._buffer[0] == "result"
    assert p._buffer.count("") >= 2
    assert p._last_command_offset == len(p._buffer)


def test_last_command_context_returns_only_recent_output():
    p = _make_panel()
    p.write("old result")
    p.mark_command_start()
    p.write("new result")
    ctx = p.last_command_context()
    assert "new result" in ctx
    assert "old result" not in ctx


def test_last_command_context_empty_immediately_after_mark():
    p = _make_panel()
    p.write("something")
    p.mark_command_start()
    assert p.last_command_context() == ""


def test_multiple_marks_track_last_offset():
    """Each mark resets the offset so context only covers the latest command."""
    p = _make_panel()
    p.write("cmd1 output")
    p.mark_command_start()
    p.write("cmd2 output")
    p.mark_command_start()
    p.write("cmd3 output")
    ctx = p.last_command_context()
    assert "cmd3 output" in ctx
    assert "cmd1 output" not in ctx
    assert "cmd2 output" not in ctx


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_resets_buffer_and_offset():
    p = _make_panel()
    p.write("data")
    p.mark_command_start()
    p.write("more data")
    p.clear()
    assert p._buffer == []
    assert p._last_command_offset == 0


def test_clear_does_not_affect_utility_buffer():
    p = _make_panel()
    p.show_utility()
    p.write("config info")
    p.show_search()
    p.clear()
    assert "config info" in p._utility_buffer


# ---------------------------------------------------------------------------
# write routing by mode
# ---------------------------------------------------------------------------

def test_write_search_mode_appends_to_buffer():
    p = _make_panel()
    p.write("search result")
    assert "search result" in p._buffer
    assert "search result" not in p._utility_buffer


def test_write_utility_mode_appends_to_utility_buffer():
    p = _make_panel()
    p.show_utility()
    p.write("config output")
    assert "config output" in p._utility_buffer
    assert "config output" not in p._buffer


def test_write_header_search_mode_appends_to_buffer():
    p = _make_panel()
    p.write_header("/yara")
    assert any("/yara" in line for line in p._buffer)
    assert p._utility_buffer == []


def test_write_header_utility_mode_appends_to_utility_buffer():
    p = _make_panel()
    p.show_utility()
    p.write_header("/config")
    assert any("/config" in line for line in p._utility_buffer)
    assert not any("/config" in line for line in p._buffer)


# ---------------------------------------------------------------------------
# show_utility / show_search
# ---------------------------------------------------------------------------

def test_show_utility_sets_utility_mode():
    p = _make_panel()
    p.show_utility()
    assert p._utility_mode is True


def test_show_utility_clears_utility_buffer():
    p = _make_panel()
    p.show_utility()
    p.write("stale output")
    p.show_utility()
    assert p._utility_buffer == []


def test_show_utility_does_not_clear_search_buffer():
    p = _make_panel()
    p.write("search result")
    p.show_utility()
    assert "search result" in p._buffer


def test_show_search_clears_utility_mode():
    p = _make_panel()
    p.show_utility()
    p.show_search()
    assert p._utility_mode is False


def test_show_search_writes_go_to_search_buffer():
    p = _make_panel()
    p.show_utility()
    p.write("utility text")
    p.show_search()
    p.write("search text")
    assert "search text" in p._buffer
    assert "search text" not in p._utility_buffer


def test_search_buffer_preserved_across_utility_roundtrip():
    """Search results survive a show_utility() → show_search() cycle."""
    p = _make_panel()
    p.write("yara hit")
    p.show_utility()
    p.write("config info")
    p.show_search()
    assert "yara hit" in p._buffer
    assert "config info" not in p._buffer
