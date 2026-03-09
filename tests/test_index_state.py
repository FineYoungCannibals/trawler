from __future__ import annotations

import time
from pathlib import Path

from trawler.index_state import IndexState


def test_fresh_state_has_no_records(tmp_state):
    state = IndexState()
    assert len(state._records) == 0


def test_mark_indexed_and_is_current(tmp_state, tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")

    state = IndexState()
    state.mark_indexed(f)

    assert state.is_current(f)


def test_is_current_false_for_unknown_file(tmp_state, tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")

    state = IndexState()
    assert not state.is_current(f)


def test_is_current_false_after_file_modified(tmp_state, tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")

    state = IndexState()
    state.mark_indexed(f)

    # Modify the file — mtime and size change
    f.write_text("hello world extended")
    assert not state.is_current(f)


def test_state_persists_across_instances(tmp_state, tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")

    state = IndexState()
    state.mark_indexed(f)

    reloaded = IndexState()
    assert reloaded.is_current(f)


def test_dir_status_empty_directory(tmp_state, tmp_path):
    d = tmp_path / "empty"
    d.mkdir()

    state = IndexState()
    result = state.dir_status([str(d)])
    s = result[str(d)]

    assert s["total"] == 0
    assert s["eligible"] == 0
    assert s["indexed"] == 0
    assert s["oversized"] == 0
    assert s["type_skipped_exts"] == {}


def test_dir_status_counts_files(tmp_state, tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "a.txt").write_text("hello")
    (d / "b.txt").write_text("world")

    state = IndexState()
    result = state.dir_status([str(d)], index_extensions=[".txt"])
    s = result[str(d)]

    assert s["total"] == 2
    assert s["eligible"] == 2
    assert s["indexed"] == 0


def test_dir_status_type_skipped(tmp_state, tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "a.txt").write_text("hello")
    (d / "b.json").write_text("{}")
    (d / "c.csv").write_text("a,b,c")

    state = IndexState()
    result = state.dir_status([str(d)], index_extensions=[".txt"])
    s = result[str(d)]

    assert s["eligible"] == 1
    assert s["type_skipped_exts"] == {".json": 1, ".csv": 1}


def test_dir_status_oversized(tmp_state, tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    small = d / "small.txt"
    large = d / "large.txt"
    small.write_text("hi")
    large.write_bytes(b"x" * 2000)

    state = IndexState()
    result = state.dir_status([str(d)], max_file_bytes=1000)
    s = result[str(d)]

    assert s["oversized"] == 1
    assert s["eligible"] == 1


def test_dir_status_marks_indexed(tmp_state, tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    f = d / "a.txt"
    f.write_text("hello")

    state = IndexState()
    state.mark_indexed(f)

    result = state.dir_status([str(d)])
    s = result[str(d)]

    assert s["indexed"] == 1
    assert s["unindexed"] == 0


def test_dir_status_nonexistent_directory(tmp_state):
    state = IndexState()
    result = state.dir_status(["/nonexistent/path/xyz"])
    s = result["/nonexistent/path/xyz"]

    assert s["total"] == 0
    assert s["eligible"] == 0
