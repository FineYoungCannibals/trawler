from __future__ import annotations

from trawler.config import TrawlerConfig, DEFAULT_INDEX_EXTENSIONS, DEFAULT_SKIP_EXTENSIONS


def test_load_returns_defaults_when_no_file(tmp_config):
    cfg = TrawlerConfig.load()
    assert cfg.directories == []
    assert cfg.embedding_model == "all-MiniLM-L6-v2"
    assert cfg.max_file_bytes is None
    assert cfg.index_extensions == list(DEFAULT_INDEX_EXTENSIONS)
    assert cfg.skip_extensions == list(DEFAULT_SKIP_EXTENSIONS)


def test_save_creates_config_file(tmp_config):
    cfg = TrawlerConfig()
    cfg.save()
    assert (tmp_config / "config.toml").exists()


def test_save_load_roundtrip(tmp_config):
    cfg = TrawlerConfig(
        directories=["/tmp/data"],
        embedding_model="all-MiniLM-L6-v2",
        max_file_bytes=512000,
        index_extensions=[".txt", ".md"],
        skip_extensions=[".json"],
    )
    cfg.save()

    loaded = TrawlerConfig.load()
    assert loaded.directories == ["/tmp/data"]
    assert loaded.embedding_model == "all-MiniLM-L6-v2"
    assert loaded.max_file_bytes == 512000
    assert loaded.index_extensions == [".txt", ".md"]
    assert loaded.skip_extensions == [".json"]


def test_max_file_bytes_none_roundtrip(tmp_config):
    cfg = TrawlerConfig(max_file_bytes=None)
    cfg.save()
    loaded = TrawlerConfig.load()
    assert loaded.max_file_bytes is None


def test_max_file_bytes_zero_roundtrip(tmp_config):
    cfg = TrawlerConfig(max_file_bytes=0)
    cfg.save()
    loaded = TrawlerConfig.load()
    assert loaded.max_file_bytes == 0


def test_add_directory(tmp_config):
    cfg = TrawlerConfig()
    cfg.add_directory("/tmp/foo")
    assert "/tmp/foo" in cfg.directories

    loaded = TrawlerConfig.load()
    assert "/tmp/foo" in loaded.directories


def test_add_directory_no_duplicates(tmp_config):
    cfg = TrawlerConfig()
    cfg.add_directory("/tmp/foo")
    cfg.add_directory("/tmp/foo")
    assert cfg.directories.count("/tmp/foo") == 1


def test_remove_directory(tmp_config):
    cfg = TrawlerConfig(directories=["/tmp/foo", "/tmp/bar"])
    cfg.save()
    cfg.remove_directory("/tmp/foo")
    assert "/tmp/foo" not in cfg.directories

    loaded = TrawlerConfig.load()
    assert "/tmp/foo" not in loaded.directories
    assert "/tmp/bar" in loaded.directories


def test_remove_directory_nonexistent_is_noop(tmp_config):
    cfg = TrawlerConfig(directories=["/tmp/foo"])
    cfg.save()
    cfg.remove_directory("/tmp/does-not-exist")
    assert cfg.directories == ["/tmp/foo"]
