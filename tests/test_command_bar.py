"""Tests for trawler.widgets.command_bar helpers."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from trawler.widgets.command_bar import CommandSuggester, _complete_fs_path


# ---------------------------------------------------------------------------
# _complete_fs_path
# ---------------------------------------------------------------------------

def test_complete_fs_path_partial_name(tmp_path):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    result = _complete_fs_path(str(tmp_path / "al"))
    assert result is not None
    assert result.endswith("alpha/") or result.endswith("alpha\\")


def test_complete_fs_path_trailing_sep_suggests_child(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "child").mkdir()
    path_str = str(parent) + "/"
    result = _complete_fs_path(path_str)
    assert result is not None
    assert "child" in result


def test_complete_fs_path_empty_returns_none():
    assert _complete_fs_path("") is None


def test_complete_fs_path_no_match_returns_none(tmp_path):
    result = _complete_fs_path(str(tmp_path / "zzz_no_such_dir"))
    assert result is None


def test_complete_fs_path_skips_hidden_dirs(tmp_path):
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible").mkdir()
    path_str = str(tmp_path) + "/"
    result = _complete_fs_path(path_str)
    assert result is not None
    assert ".hidden" not in result
    assert "visible" in result


def test_complete_fs_path_permission_error_returns_none(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise PermissionError("no access")
    monkeypatch.setattr(Path, "iterdir", boom)
    result = _complete_fs_path(str(tmp_path) + "/")
    assert result is None


# ---------------------------------------------------------------------------
# CommandSuggester — command completion
# ---------------------------------------------------------------------------

def _suggest(value: str, get_dirs=None) -> str | None:
    suggester = CommandSuggester(get_dirs=get_dirs)
    return asyncio.run(suggester.get_suggestion(value))


def test_suggests_command_prefix():
    result = _suggest("/sea")
    assert result == "/search"


def test_no_suggestion_for_exact_command():
    assert _suggest("/search") is None


def test_no_suggestion_for_unknown():
    assert _suggest("/zzz") is None


def test_skips_ghost_starting_with_space():
    # "/config" would suggest "/config path" — ghost starts with " ", should skip
    assert _suggest("/config") is None


def test_subcommand_completion_after_space():
    # After "/config " the ghost for "/config path" is "path" — no leading space
    result = _suggest("/config ")
    assert result == "/config path"


# ---------------------------------------------------------------------------
# CommandSuggester — /config path rm autocomplete
# ---------------------------------------------------------------------------

def test_rm_suggests_configured_dir():
    dirs = ["/data/breach", "/data/drops"]
    result = _suggest("/config path rm /data/b", get_dirs=lambda: dirs)
    assert result == "/config path rm /data/breach"


def test_rm_exact_match_returns_none():
    dirs = ["/data/breach"]
    result = _suggest("/config path rm /data/breach", get_dirs=lambda: dirs)
    assert result is None


def test_rm_no_dirs_returns_none():
    result = _suggest("/config path rm /data/", get_dirs=lambda: [])
    assert result is None


def test_rm_get_dirs_exception_returns_none():
    def bad_dirs():
        raise RuntimeError("oops")
    result = _suggest("/config path rm /data/", get_dirs=bad_dirs)
    assert result is None


# ---------------------------------------------------------------------------
# CommandSuggester — --dir filesystem completion
# ---------------------------------------------------------------------------

def test_dir_flag_completes_path(tmp_path):
    (tmp_path / "drops").mkdir()
    partial = str(tmp_path) + "/dr"
    value = f"/search passwords --dir {partial}"
    result = _suggest(value)
    assert result is not None
    assert result.startswith("/search passwords --dir ")
    assert "drops" in result


def test_dir_flag_after_rg_options(tmp_path):
    (tmp_path / "archive").mkdir()
    partial = str(tmp_path) + "/arc"
    value = f"/rg -i email --dir {partial}"
    result = _suggest(value)
    assert result is not None
    assert result.startswith("/rg -i email --dir ")
    assert "archive" in result


def test_dir_flag_no_match_returns_none(tmp_path):
    value = f"/search foo --dir {tmp_path}/zzz_no_such"
    result = _suggest(value)
    assert result is None
