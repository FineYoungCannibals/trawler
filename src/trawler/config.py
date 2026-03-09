from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import tomli
import tomli_w

DEFAULT_INDEX_EXTENSIONS = [
    ".txt", ".md", ".rst", ".text",
    ".html", ".htm",
    ".eml", ".mbox",
    ".log",
]

DEFAULT_SKIP_EXTENSIONS = [
    ".json", ".csv", ".tsv", ".xml",
    ".sql", ".db", ".sqlite", ".sqlite3",
    ".gz", ".zip", ".tar", ".bz2", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico",
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".mp3", ".mp4", ".avi", ".mov",
    ".exe", ".dll", ".so", ".dylib",
    ".bin", ".dat",
]

CONFIG_DIR = Path.cwd() / ".trawler"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class TrawlerConfig:
    directories: list[str] = field(default_factory=list)
    embedding_model: str = "all-MiniLM-L6-v2"
    # None = not yet set (modal will appear on first /index)
    # 0    = no limit (user explicitly chose unlimited)
    # >0   = max file size in bytes
    max_file_bytes: int | None = None
    index_extensions: list[str] = field(default_factory=lambda: list(DEFAULT_INDEX_EXTENSIONS))
    skip_extensions: list[str] = field(default_factory=lambda: list(DEFAULT_SKIP_EXTENSIONS))

    @classmethod
    def load(cls) -> TrawlerConfig:
        if not CONFIG_FILE.exists():
            return cls()
        with open(CONFIG_FILE, "rb") as f:
            data = tomli.load(f)
        dirs = [d["path"] for d in data.get("directories", [])]
        trawler = data.get("trawler", {})
        model = trawler.get("embedding_model", "all-MiniLM-L6-v2")
        raw_limit = trawler.get("max_file_bytes")
        max_file_bytes = int(raw_limit) if raw_limit is not None else None
        index_extensions_raw = trawler.get("index_extensions")
        index_extensions = index_extensions_raw if index_extensions_raw is not None else list(DEFAULT_INDEX_EXTENSIONS)
        skip_extensions_raw = trawler.get("skip_extensions")
        skip_extensions = skip_extensions_raw if skip_extensions_raw is not None else list(DEFAULT_SKIP_EXTENSIONS)
        return cls(directories=dirs, embedding_model=model, max_file_bytes=max_file_bytes, index_extensions=index_extensions, skip_extensions=skip_extensions)

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        trawler_section: dict = {"embedding_model": self.embedding_model}
        if self.max_file_bytes is not None:
            trawler_section["max_file_bytes"] = self.max_file_bytes
        trawler_section["index_extensions"] = self.index_extensions
        trawler_section["skip_extensions"] = self.skip_extensions
        data: dict = {
            "trawler": trawler_section,
            "directories": [{"path": d} for d in self.directories],
        }
        with open(CONFIG_FILE, "wb") as f:
            tomli_w.dump(data, f)

    def add_directory(self, path: str) -> None:
        if path not in self.directories:
            self.directories.append(path)
            self.save()

    def remove_directory(self, path: str) -> None:
        if path in self.directories:
            self.directories.remove(path)
            self.save()
