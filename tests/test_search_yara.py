from __future__ import annotations

from trawler.search.yara_scan import scan


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
