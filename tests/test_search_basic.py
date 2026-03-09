from __future__ import annotations

from trawler.search.basic import search


def _collect(pattern, directories):
    return list(search(pattern, directories))


def test_finds_match(data_dir):
    results = _collect("support@example.com", [str(data_dir)])
    assert any("support@example.com" in r for r in results)


def test_includes_filename_and_lineno(data_dir):
    results = _collect("support@example.com", [str(data_dir)])
    match = next(r for r in results if "support@example.com" in r)
    assert "emails.txt" in match
    assert "1" in match  # line number


def test_no_match_returns_no_results_message(data_dir):
    results = _collect("zzznomatchzzz", [str(data_dir)])
    assert len(results) == 1
    assert "No matches" in results[0]


def test_regex_pattern(data_dir):
    results = _collect(r"\w+@\w+\.\w+", [str(data_dir)])
    assert any("emails.txt" in r for r in results)


def test_invalid_regex_falls_back_to_literal(data_dir):
    # "[unclosed" is invalid regex — should fall back to literal search
    results = _collect("[unclosed", [str(data_dir)])
    # Should not raise, should return no-match message (no file contains "[unclosed")
    assert isinstance(results, list)


def test_no_directories_returns_warning():
    results = _collect("anything", [])
    assert len(results) == 1
    assert "No directories" in results[0]


def test_nonexistent_directory_reports_error():
    results = _collect("anything", ["/nonexistent/path/xyz"])
    assert any("Not a directory" in r for r in results)


def test_multiple_files_searched(data_dir):
    results = _collect(".", [str(data_dir)])
    filenames = {r.split(":")[0] for r in results if ":" in r}
    # All three files should appear in results
    assert any("emails.txt" in f for f in filenames)
    assert any("creds.txt" in f for f in filenames)
    assert any("notes.md" in f for f in filenames)
