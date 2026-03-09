from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect config storage to a temp directory."""
    import trawler.config as cfg_module
    trawler_dir = tmp_path / ".trawler"
    monkeypatch.setattr(cfg_module, "CONFIG_DIR", trawler_dir)
    monkeypatch.setattr(cfg_module, "CONFIG_FILE", trawler_dir / "config.toml")
    return trawler_dir


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """Redirect index state storage to a temp directory."""
    import trawler.index_state as is_module
    state_file = tmp_path / ".trawler" / "index_state.json"
    monkeypatch.setattr(is_module, "STATE_FILE", state_file)
    return state_file


@pytest.fixture
def data_dir(tmp_path):
    """A temporary directory pre-populated with a handful of text files."""
    d = tmp_path / "data"
    d.mkdir()
    (d / "emails.txt").write_text(
        "contact us at support@example.com for help\n"
        "also reach admin@corp.org\n"
    )
    (d / "creds.txt").write_text(
        "username:password123\n"
        "password=hunter2\n"
    )
    (d / "notes.md").write_text(
        "# Meeting notes\nDiscussed the quarterly review.\n"
    )
    return d
