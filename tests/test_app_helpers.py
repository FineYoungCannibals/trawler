"""Tests for pure helper methods on TrawlerApp."""
from __future__ import annotations

from trawler.app import TrawlerApp

_parse = TrawlerApp._parse_dir_flag


# ---------------------------------------------------------------------------
# _parse_dir_flag
# ---------------------------------------------------------------------------

def test_no_dir_flag_returns_args_unchanged():
    cleaned, path = _parse("passwords")
    assert cleaned == "passwords"
    assert path is None


def test_dir_flag_at_end():
    cleaned, path = _parse("passwords --dir /data/drops")
    assert cleaned == "passwords"
    assert path == "/data/drops"


def test_dir_flag_in_middle():
    cleaned, path = _parse("--dir /data/drops passwords")
    assert cleaned == "passwords"
    assert path == "/data/drops"


def test_dir_flag_with_rg_options():
    cleaned, path = _parse("-i email --dir /data/breach")
    assert cleaned == "-i email"
    assert path == "/data/breach"


def test_dir_flag_quoted_path_with_spaces():
    cleaned, path = _parse('passwords --dir "/my data/drops folder"')
    assert cleaned == "passwords"
    assert path == "/my data/drops folder"


def test_dir_flag_missing_value_ignored():
    # shlex parses fine; "--dir" with nothing after is left in cleaned args
    cleaned, path = _parse("passwords --dir")
    assert path is None
    assert "--dir" in cleaned


def test_no_args_returns_empty():
    cleaned, path = _parse("")
    assert cleaned == ""
    assert path is None


def test_only_dir_flag():
    cleaned, path = _parse("--dir /data")
    assert cleaned == ""
    assert path == "/data"


def test_windows_style_path_quoted():
    # Unquoted backslashes are escape chars in shlex (POSIX mode); quote the path
    cleaned, path = _parse(r'passwords --dir "C:\Users\analyst\drops"')
    assert cleaned == "passwords"
    assert path == r"C:\Users\analyst\drops"


# ---------------------------------------------------------------------------
# _resolve_dir_filter — fallback for unquoted paths with spaces
# ---------------------------------------------------------------------------

def _make_app_with_dirs(dirs):
    """Create a TrawlerApp-like object with config.directories set."""
    from unittest.mock import MagicMock
    app = TrawlerApp.__new__(TrawlerApp)
    app.config = MagicMock()
    app.config.directories = dirs
    return app


def test_resolve_exact_match():
    app = _make_app_with_dirs(["/data/breach"])
    cleaned, d = app._resolve_dir_filter(
        "pattern --dir /data/breach", "/data/breach", "pattern",
    )
    assert d == "/data/breach"
    assert cleaned == "pattern"


def test_resolve_none_dir():
    app = _make_app_with_dirs(["/data/breach"])
    cleaned, d = app._resolve_dir_filter("pattern", None, "pattern")
    assert d is None
    assert cleaned == "pattern"


def test_resolve_unquoted_path_with_spaces():
    """Unquoted path with spaces — shlex merges path+query; resolver fixes it."""
    dirs = ["/Users/me/Documents/Epstein Files/VOL00012/IMAGES/0001/"]
    app = _make_app_with_dirs(dirs)
    raw_args = "--dir /Users/me/Documents/Epstein Files/VOL00012/IMAGES/0001/ find emails"
    # shlex would parse this wrong — simulate what _parse_dir_flag returns
    shlex_cleaned, shlex_dir = _parse(raw_args)
    cleaned, d = app._resolve_dir_filter(raw_args, shlex_dir, shlex_cleaned)
    assert d == dirs[0]
    assert "find" in cleaned
    assert "emails" in cleaned


def test_resolve_unquoted_no_configured_match():
    app = _make_app_with_dirs(["/data/breach"])
    cleaned, d = app._resolve_dir_filter(
        "pattern --dir /other/path", "/other/path", "pattern",
    )
    # No match — returns dir_filter unchanged for error handling upstream
    assert d == "/other/path"
    assert cleaned == "pattern"


def test_resolve_picks_longest_match():
    dirs = ["/data/", "/data/breach/deep/"]
    app = _make_app_with_dirs(dirs)
    raw_args = "--dir /data/breach/deep/ query"
    shlex_cleaned, shlex_dir = _parse(raw_args)
    cleaned, d = app._resolve_dir_filter(raw_args, shlex_dir, shlex_cleaned)
    assert d == "/data/breach/deep/"
