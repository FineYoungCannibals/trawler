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
