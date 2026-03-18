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
    ".pdf", ".docx",
]

DEFAULT_SKIP_EXTENSIONS = [
    ".json", ".csv", ".tsv", ".xml",
    ".sql", ".db", ".sqlite", ".sqlite3",
    ".gz", ".zip", ".tar", ".bz2", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico",
    ".xlsx", ".pptx",
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
    # None = use bundled src/trawler/rules/
    rules_dir: str | None = None
    # None = no proxy; set to e.g. "http://proxy.corp.com:8080"
    proxy: str | None = None
    # LLM settings (Phase 6)
    # None = LLM disabled; model ID (HF hub ID or local path) for local backends
    llm_model: str | None = None
    # "mlx" (Apple Silicon), "llama-cpp" (cross-platform), "remote" (OpenAI-compat endpoint)
    llm_backend: str = "mlx"
    # max tokens of context sent to LLM (~4 chars per token)
    llm_context_tokens: int = 2048
    # remote endpoint base URL, e.g. "http://192.168.1.50:11434"
    llm_remote_url: str | None = None
    # optional API key for remote endpoint
    llm_remote_api_key: str | None = None
    # optional system prompt sent before user message; None = no system prompt
    llm_system_prompt: str | None = None
    # number of top results returned by semantic search
    topk: int = 8
    # Optional extra HTTP headers sent with every remote LLM request.
    # Merged on top of defaults (Content-Type, Authorization).
    # User-supplied headers win — they can override Content-Type and even
    # Authorization if needed.
    # Configured via [trawler.llm_remote_headers] in config.toml:
    #   [trawler.llm_remote_headers]
    #   X-Custom-Header = "value"
    llm_remote_headers: dict[str, str] = field(default_factory=dict)
    # Optional OAuth 2.0 client credentials grant configuration.
    # When present, a Bearer token is fetched (and cached until expiry)
    # before each remote LLM request.  Takes priority over llm_remote_api_key.
    # Required keys: auth_url, client_id, client_secret.  Optional: scope.
    # Configured via [trawler.llm_oauth] in config.toml:
    #   [trawler.llm_oauth]
    #   auth_url = "https://auth.corp.com/oauth2/token"
    #   client_id = "my-client-id"
    #   client_secret = "my-client-secret"
    #   scope = "llm.access"
    llm_oauth: dict[str, str] | None = None

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
        rules_dir = trawler.get("rules_dir") or None
        proxy = trawler.get("proxy") or None
        llm_model = trawler.get("llm_model") or None
        llm_backend = trawler.get("llm_backend", "mlx")
        llm_context_tokens = int(trawler.get("llm_context_tokens", 2048))
        llm_remote_url = trawler.get("llm_remote_url") or None
        llm_remote_api_key = trawler.get("llm_remote_api_key") or None
        llm_system_prompt = trawler.get("llm_system_prompt") or None
        topk = int(trawler.get("topk", 8))
        llm_remote_headers = trawler.get("llm_remote_headers", {})
        llm_oauth_raw = trawler.get("llm_oauth")
        llm_oauth = dict(llm_oauth_raw) if llm_oauth_raw else None
        return cls(
            directories=dirs,
            embedding_model=model,
            max_file_bytes=max_file_bytes,
            index_extensions=index_extensions,
            skip_extensions=skip_extensions,
            rules_dir=rules_dir,
            proxy=proxy,
            llm_model=llm_model,
            llm_backend=llm_backend,
            llm_context_tokens=llm_context_tokens,
            llm_remote_url=llm_remote_url,
            llm_remote_api_key=llm_remote_api_key,
            llm_system_prompt=llm_system_prompt,
            topk=topk,
            llm_remote_headers=llm_remote_headers,
            llm_oauth=llm_oauth,
        )

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        trawler_section: dict = {"embedding_model": self.embedding_model}
        if self.max_file_bytes is not None:
            trawler_section["max_file_bytes"] = self.max_file_bytes
        trawler_section["index_extensions"] = self.index_extensions
        trawler_section["skip_extensions"] = self.skip_extensions
        if self.rules_dir is not None:
            trawler_section["rules_dir"] = self.rules_dir
        if self.proxy is not None:
            trawler_section["proxy"] = self.proxy
        if self.llm_model is not None:
            trawler_section["llm_model"] = self.llm_model
        trawler_section["llm_backend"] = self.llm_backend
        trawler_section["llm_context_tokens"] = self.llm_context_tokens
        if self.llm_remote_url is not None:
            trawler_section["llm_remote_url"] = self.llm_remote_url
        if self.llm_remote_api_key is not None:
            trawler_section["llm_remote_api_key"] = self.llm_remote_api_key
        if self.llm_system_prompt is not None:
            trawler_section["llm_system_prompt"] = self.llm_system_prompt
        trawler_section["topk"] = self.topk
        if self.llm_remote_headers:
            trawler_section["llm_remote_headers"] = self.llm_remote_headers
        if self.llm_oauth is not None:
            trawler_section["llm_oauth"] = self.llm_oauth
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
