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


# ---------------------------------------------------------------------------
# prune_deleted
# ---------------------------------------------------------------------------

def test_prune_deleted_removes_missing_files(tmp_state, tmp_path):
    f = tmp_path / "gone.txt"
    f.write_text("data")

    state = IndexState()
    state.mark_indexed(f)
    assert state.is_current(f)

    f.unlink()
    removed = state.prune_deleted()

    assert removed == 1
    assert str(f) not in state._records


def test_prune_deleted_keeps_existing_files(tmp_state, tmp_path):
    f = tmp_path / "alive.txt"
    f.write_text("data")

    state = IndexState()
    state.mark_indexed(f)

    removed = state.prune_deleted()

    assert removed == 0
    assert str(f) in state._records


def test_prune_deleted_persists_changes(tmp_state, tmp_path):
    f = tmp_path / "ephemeral.txt"
    f.write_text("data")

    state = IndexState()
    state.mark_indexed(f)
    f.unlink()
    state.prune_deleted()

    reloaded = IndexState()
    assert str(f) not in reloaded._records


def test_prune_deleted_empty_state(tmp_state):
    state = IndexState()
    removed = state.prune_deleted()
    assert removed == 0


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_removes_all_records(tmp_state, tmp_path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("a")
    f2.write_text("b")

    state = IndexState()
    state.mark_indexed(f1)
    state.mark_indexed(f2)
    assert len(state._records) == 2

    state.clear()
    assert len(state._records) == 0


def test_clear_persists_to_disk(tmp_state, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("a")

    state = IndexState()
    state.mark_indexed(f)
    state.clear()

    reloaded = IndexState()
    assert len(reloaded._records) == 0


# ---------------------------------------------------------------------------
# stale index state scenario: directory removed then re-added
# ---------------------------------------------------------------------------

def test_prune_deleted_enables_reindex_after_dir_recreated(tmp_state, tmp_path):
    """
    Simulates: index dir → delete dir → recreate dir with same files →
    prune_deleted should clear stale entries so files are seen as unindexed.
    """
    d = tmp_path / "data"
    d.mkdir()
    f = d / "file.txt"
    f.write_text("original content")

    state = IndexState()
    state.mark_indexed(f)
    assert list(state.unindexed_files([str(d)])) == []

    # Simulate directory being deleted
    f.unlink()
    d.rmdir()

    state.prune_deleted()

    # Recreate directory with the same file
    d.mkdir()
    f.write_text("original content")

    # File should now appear as unindexed (stale entry was pruned)
    unindexed = list(state.unindexed_files([str(d)]))
    assert f in unindexed
