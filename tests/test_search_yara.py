from __future__ import annotations

import threading

from trawler.search.yara_scan import _get_line_context, _safe_value, scan


def _collect(pattern, directories):
    return list(scan(pattern, directories))


def test_email_rule_matches(data_dir):
    results = _collect(None, [str(data_dir)])
    assert any("email_address" in r for r in results)


def test_credential_rule_matches(data_dir):
    results = _collect(None, [str(data_dir)])
    assert any("credential_pattern" in r for r in results)


def test_glob_filter_matches_correct_rule(data_dir):
    results = _collect("email*", [str(data_dir)])
    assert any("email_address" in r for r in results)
    assert not any("credential_pattern" in r for r in results)


def test_glob_filter_excludes_nonmatching(data_dir):
    results = _collect("credential*", [str(data_dir)])
    assert any("credential_pattern" in r for r in results)
    assert not any("email_address" in r for r in results)


def test_wildcard_pattern_matches_all(data_dir):
    results = _collect("*", [str(data_dir)])
    assert any("email_address" in r for r in results)
    assert any("credential_pattern" in r for r in results)


def test_no_match_returns_no_match_message(tmp_path):
    # File with no emails or credentials
    d = tmp_path / "clean"
    d.mkdir()
    (d / "plain.txt").write_text("nothing interesting here\n")

    results = _collect(None, [str(d)])
    assert len(results) == 1
    assert "No YARA matches" in results[0]


def test_no_directories_returns_warning():
    results = _collect(None, [])
    assert len(results) == 1
    assert "No directories" in results[0]


def test_nonexistent_directory_reports_error():
    results = _collect(None, ["/nonexistent/path/xyz"])
    assert any("Not a directory" in r for r in results)


def test_matched_file_shown_in_output(data_dir):
    results = _collect(None, [str(data_dir)])
    assert any("emails.txt" in r for r in results)


def test_custom_rules_dir(tmp_path, data_dir):
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "custom.yar").write_text("""
rule custom_keyword {
    strings:
        $kw = "quarterly"
    condition:
        $kw
}
""")
    results = list(scan(None, [str(data_dir)], rules_dir=str(rules_dir)))
    assert any("custom_keyword" in r for r in results)
    # Bundled rules should NOT have run
    assert not any("email_address" in r for r in results)


def test_custom_rules_dir_empty_reports_warning(tmp_path, data_dir):
    empty_rules = tmp_path / "empty-rules"
    empty_rules.mkdir()
    results = list(scan(None, [str(data_dir)], rules_dir=str(empty_rules)))
    assert len(results) == 1
    assert "No YARA rules found" in results[0]


def test_default_rules_dir_used_when_none(data_dir):
    # Passing rules_dir=None should fall back to bundled rules
    results = list(scan(None, [str(data_dir)], rules_dir=None))
    assert any("email_address" in r for r in results)


# ---------------------------------------------------------------------------
# _safe_value — matched-data sanitisation
# ---------------------------------------------------------------------------

def test_safe_value_clean_ascii_passthrough():
    assert _safe_value(b"hello world") == "hello world"


def test_safe_value_strips_ansi_color_codes():
    # ESC[31m...ESC[0m — SGR color sequences
    data = b"\x1b[31mred text\x1b[0m"
    result = _safe_value(data)
    assert "\x1b" not in result
    assert "red text" in result


def test_safe_value_strips_carriage_return():
    data = b"line one\r\nline two"
    result = _safe_value(data)
    assert "\r" not in result
    assert "\n" not in result


def test_safe_value_strips_null_and_control_chars():
    data = b"before\x00\x01\x07\x1fafter"
    result = _safe_value(data)
    for ch in ("\x00", "\x01", "\x07", "\x1f"):
        assert ch not in result
    assert "before" in result
    assert "after" in result


def test_safe_value_strips_escape_char_alone():
    data = b"text \x1b more text"
    result = _safe_value(data)
    assert "\x1b" not in result
    assert "text" in result
    assert "more text" in result


def test_safe_value_truncates_long_data():
    data = b"A" * 300
    result = _safe_value(data)
    assert result.endswith("…")
    # Should not exceed 200 visible chars + ellipsis
    assert len(result) <= 202


def test_safe_value_no_truncation_at_limit():
    data = b"B" * 200
    result = _safe_value(data)
    assert result == "B" * 200
    assert "…" not in result


def test_safe_value_binary_replacement_chars_are_safe():
    # Non-UTF-8 bytes become replacement chars U+FFFD, which are harmless
    data = b"\xff\xfe\xfd"
    result = _safe_value(data)
    assert "\x1b" not in result
    assert "\r" not in result


def test_safe_value_escapes_rich_markup():
    # Square brackets are escaped with \ so Rich doesn't treat them as markup tags.
    # rich.markup.escape("[bold]") → r"\[bold]"
    data = b"[bold]not markup[/bold]"
    result = _safe_value(data)
    assert result.startswith(r"\[")   # leading [ is backslash-escaped
    assert "bold" in result           # text content preserved


def test_safe_value_osc_sequence_stripped():
    # OSC sequence: ESC ] ... BEL
    data = b"\x1b]0;window title\x07normal text"
    result = _safe_value(data)
    assert "\x1b" not in result
    assert "window title" not in result
    assert "normal text" in result


# ---------------------------------------------------------------------------
# stop_event / on_progress — cancellation and progress reporting
# ---------------------------------------------------------------------------

def test_stop_event_pre_set_returns_early(data_dir):
    """A pre-set stop_event should cause scan to produce no match results."""
    ev = threading.Event()
    ev.set()
    results = list(scan(None, [str(data_dir)], stop_event=ev))
    # Should have stopped before scanning any files — no match lines
    assert not any("[YARA]" in r for r in results)


def test_on_progress_called(tmp_path):
    """on_progress should fire after every _PROGRESS_INTERVAL files."""
    d = tmp_path / "many"
    d.mkdir()
    # Create 150 tiny files so progress fires at least once (interval=100)
    for i in range(150):
        (d / f"f{i}.txt").write_text(f"data {i}\n")
    counts = []
    results = list(scan(None, [str(d)], on_progress=lambda n: counts.append(n)))
    assert len(counts) >= 1
    assert counts[0] == 100


def test_stop_event_via_progress_callback(tmp_path):
    """Setting stop_event inside the progress callback stops the scan."""
    d = tmp_path / "many"
    d.mkdir()
    for i in range(250):
        (d / f"f{i}.txt").write_text(f"data {i}\n")

    ev = threading.Event()
    progress_calls = []

    def on_progress(n):
        progress_calls.append(n)
        ev.set()  # cancel after first progress callback

    results = list(scan(None, [str(d)], stop_event=ev, on_progress=on_progress))
    # Should have stopped around 100 files, not processed all 250
    assert len(progress_calls) == 1


# ---------------------------------------------------------------------------
# _get_line_context — byte offset → line number + context
# ---------------------------------------------------------------------------

def test_get_line_context_single_line():
    content = b"hello world"
    result = _get_line_context(content, 6)
    assert result is not None
    lineno, text = result
    assert lineno == 1
    assert "hello world" in text


def test_get_line_context_multiline():
    content = b"line one\nline two\nline three\n"
    # offset 10 is in "line two"
    result = _get_line_context(content, 10)
    assert result is not None
    lineno, text = result
    assert lineno == 2
    assert "line two" in text


def test_get_line_context_last_line_no_newline():
    content = b"first\nsecond\nthird"
    # offset 14 is in "third"
    result = _get_line_context(content, 14)
    assert result is not None
    lineno, text = result
    assert lineno == 3
    assert "third" in text


def test_get_line_context_binary_returns_none():
    # Mostly non-UTF-8 bytes → high replacement ratio → binary
    content = bytes(range(128, 256))
    result = _get_line_context(content, 10)
    assert result is None


def test_get_line_context_strips_control_chars():
    content = b"clean\nhas \x07bell \x01soh here\nnext"
    result = _get_line_context(content, 8)
    assert result is not None
    _, text = result
    assert "\x07" not in text
    assert "\x01" not in text
    assert "bell" in text


# ---------------------------------------------------------------------------
# Line context in scan output
# ---------------------------------------------------------------------------

def test_scan_text_file_shows_line_context(data_dir):
    """Text file matches should show 'line N' and the matched line content."""
    results = _collect(None, [str(data_dir)])
    # Find a match line (not the header)
    match_lines = [r for r in results if r.strip().startswith("[dim]line")]
    assert len(match_lines) > 0, "Expected 'line N' output for text file matches"

    # The line after a "line N" entry should be the context line
    for i, r in enumerate(results):
        if r.strip().startswith("[dim]line"):
            assert i + 1 < len(results), "Expected context line after match"
            ctx_line = results[i + 1]
            # Context lines are indented with 4 spaces
            assert ctx_line.startswith("    "), f"Context line should be indented: {ctx_line!r}"


def test_scan_binary_file_shows_offset(tmp_path):
    """Binary file matches should fall back to 'offset N' display."""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "magic.yar").write_text("""
rule find_magic {
    strings:
        $m = { CA FE }
    condition:
        $m
}
""")
    d = tmp_path / "bindata"
    d.mkdir()
    # Write binary content with the target bytes
    (d / "blob.bin").write_bytes(b"\xff\xfe\xfd\xca\xfe\x80\x81\x82\x83\x84")

    results = list(scan(None, [str(d)], rules_dir=str(rules_dir)))
    match_lines = [r for r in results if "offset" in r]
    assert len(match_lines) > 0, "Binary file matches should show 'offset N'"
