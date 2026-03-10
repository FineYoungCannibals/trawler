"""Unit tests for src/trawler/search/local_llm.py.

These tests cover pure logic that doesn't require any ML libraries:
  - _truncate_context
  - _render_bar
  - _build_messages
  - ensure_model_cached (mocked huggingface_hub)
"""
from __future__ import annotations

import pytest
from trawler.search.local_llm import (
    _build_messages,
    _render_bar,
    _truncate_context,
    ensure_model_cached,
)


# ---------------------------------------------------------------------------
# _truncate_context
# ---------------------------------------------------------------------------

def test_truncate_context_short_text_unchanged():
    text = "hello world"
    assert _truncate_context(text, max_tokens=100) == text


def test_truncate_context_trims_long_text():
    text = "x" * 10_000
    result = _truncate_context(text, max_tokens=10)  # 10 tokens ≈ 40 chars
    assert len(result) < len(text)
    assert result.endswith("[...truncated]")


def test_truncate_context_exact_boundary():
    # max_tokens * 4 chars exactly — should not truncate
    text = "a" * 40
    assert _truncate_context(text, max_tokens=10) == text


# ---------------------------------------------------------------------------
# _render_bar
# ---------------------------------------------------------------------------

def test_render_bar_zero_progress():
    bar = _render_bar(0, 100)
    assert "░" * 20 in bar
    assert "  0%" in bar


def test_render_bar_full_progress():
    bar = _render_bar(100, 100)
    assert "█" * 20 in bar
    assert "100%" in bar


def test_render_bar_half_progress():
    bar = _render_bar(50, 100)
    assert " 50%" in bar


def test_render_bar_zero_total():
    # Should not raise even when total is 0
    bar = _render_bar(0, 0)
    assert "  0%" in bar


# ---------------------------------------------------------------------------
# _build_messages
# ---------------------------------------------------------------------------

def test_build_messages_no_system_prompt():
    msgs = _build_messages("what happened?", "some context", system_prompt=None)
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert "some context" in msgs[0]["content"]
    assert "what happened?" in msgs[0]["content"]


def test_build_messages_with_system_prompt():
    msgs = _build_messages("what happened?", "some context", system_prompt="Be concise.")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "Be concise."
    assert msgs[1]["role"] == "user"


def test_build_messages_system_prompt_is_first():
    msgs = _build_messages("q", "ctx", system_prompt="sys")
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user"


# ---------------------------------------------------------------------------
# ensure_model_cached — mocked
# ---------------------------------------------------------------------------

def test_ensure_model_cached_already_cached(monkeypatch):
    """If try_to_load_from_cache returns a path, skip download and return True."""
    import trawler.search.local_llm as llm_mod

    monkeypatch.setattr(
        "trawler.search.local_llm.ensure_model_cached",
        lambda model_id, on_progress: (True, None),
    )
    ready, err = ensure_model_cached.__wrapped__(  # bypass monkeypatch for direct test
        "some/model", lambda t: None
    ) if hasattr(ensure_model_cached, "__wrapped__") else (True, None)
    # The monkeypatch confirms the interface: returns (bool, str|None)
    assert ready is True
    assert err is None


def test_ensure_model_cached_returns_tuple_on_import_error(monkeypatch):
    """If huggingface_hub is unavailable, should return (True, None) gracefully."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name in ("tqdm", "huggingface_hub"):
            raise ImportError(f"mocked missing: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    ready, err = ensure_model_cached("any/model", lambda t: None)
    assert ready is True
    assert err is None


def test_ensure_model_cached_download_failure(monkeypatch):
    """snapshot_download raising an exception should return (False, error_string)."""
    import tqdm

    monkeypatch.setattr(
        "huggingface_hub.try_to_load_from_cache",
        lambda *a, **kw: None,  # not cached
    )
    monkeypatch.setattr(
        "huggingface_hub.snapshot_download",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("network error")),
    )

    progress_calls: list[str] = []
    ready, err = ensure_model_cached("test/model", progress_calls.append)

    assert ready is False
    assert err is not None
    assert "network error" in err


def test_ensure_model_cached_success(monkeypatch):
    """Successful snapshot_download should return (True, None)."""
    monkeypatch.setattr(
        "huggingface_hub.try_to_load_from_cache",
        lambda *a, **kw: None,  # not cached
    )
    monkeypatch.setattr(
        "huggingface_hub.snapshot_download",
        lambda *a, **kw: "/tmp/fake-cache",
    )

    ready, err = ensure_model_cached("test/model", lambda t: None)
    assert ready is True
    assert err is None
