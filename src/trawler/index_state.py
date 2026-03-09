from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator

STATE_FILE = Path.cwd() / ".trawler" / "index_state.json"


@dataclass
class FileRecord:
    mtime: float
    size: int


class IndexState:
    """Tracks which files have been embedded and stored in ChromaDB."""

    def __init__(self) -> None:
        self._records: dict[str, FileRecord] = {}
        self._load()

    def _load(self) -> None:
        if STATE_FILE.exists():
            try:
                raw = json.loads(STATE_FILE.read_text())
                self._records = {
                    k: FileRecord(**v) for k, v in raw.items()
                }
            except Exception:
                self._records = {}

    def _save(self) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps({k: asdict(v) for k, v in self._records.items()}, indent=2)
        )

    def is_current(self, path: Path) -> bool:
        """Return True if the file is already indexed and hasn't changed."""
        key = str(path)
        if key not in self._records:
            return False
        try:
            stat = path.stat()
            rec = self._records[key]
            return stat.st_mtime == rec.mtime and stat.st_size == rec.size
        except OSError:
            return False

    def mark_indexed(self, path: Path) -> None:
        stat = path.stat()
        self._records[str(path)] = FileRecord(mtime=stat.st_mtime, size=stat.st_size)
        self._save()

    def unindexed_files(self, directories: list[str]) -> Iterator[Path]:
        """Yield files in the given directories that need (re-)indexing."""
        for dir_path in directories:
            p = Path(dir_path)
            if not p.is_dir():
                continue
            for file_path in p.rglob("*"):
                if file_path.is_file() and not self.is_current(file_path):
                    yield file_path

    def dir_status(
        self,
        directories: list[str],
        max_file_bytes: int | None = None,
        index_extensions: list[str] | None = None,
    ) -> dict[str, dict[str, int]]:
        """Return {dir: {total, eligible, indexed, unindexed, oversized, type_skipped_exts}} for the sidebar."""
        result = {}
        for dir_path in directories:
            p = Path(dir_path)
            if not p.is_dir():
                result[dir_path] = {"total": 0, "eligible": 0, "indexed": 0, "unindexed": 0, "oversized": 0, "type_skipped_exts": {}}
                continue
            total = eligible = indexed = oversized = 0
            type_skipped_exts: dict[str, int] = {}
            ext_set = set(index_extensions) if index_extensions else None
            for fp in p.rglob("*"):
                if not fp.is_file():
                    continue
                total += 1
                if ext_set is not None:
                    ext = fp.suffix.lower()
                    if ext not in ext_set:
                        type_skipped_exts[ext] = type_skipped_exts.get(ext, 0) + 1
                        continue
                try:
                    st = fp.stat()
                except OSError:
                    continue
                if max_file_bytes and st.st_size > max_file_bytes:
                    oversized += 1
                    continue
                eligible += 1
                key = str(fp)
                if key in self._records:
                    rec = self._records[key]
                    if st.st_mtime == rec.mtime and st.st_size == rec.size:
                        indexed += 1
            result[dir_path] = {
                "total": total,
                "eligible": eligible,
                "indexed": indexed,
                "unindexed": eligible - indexed,
                "oversized": oversized,
                "type_skipped_exts": type_skipped_exts,
            }
        return result
