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


def test_rules_dir_roundtrip(tmp_config):
    cfg = TrawlerConfig(rules_dir="/tmp/my-rules")
    cfg.save()
    loaded = TrawlerConfig.load()
    assert loaded.rules_dir == "/tmp/my-rules"


def test_rules_dir_none_roundtrip(tmp_config):
    cfg = TrawlerConfig(rules_dir=None)
    cfg.save()
    loaded = TrawlerConfig.load()
    assert loaded.rules_dir is None


def test_proxy_roundtrip(tmp_config):
    cfg = TrawlerConfig(proxy="http://proxy.corp.com:8080")
    cfg.save()
    loaded = TrawlerConfig.load()
    assert loaded.proxy == "http://proxy.corp.com:8080"


def test_proxy_none_roundtrip(tmp_config):
    cfg = TrawlerConfig(proxy=None)
    cfg.save()
    loaded = TrawlerConfig.load()
    assert loaded.proxy is None


def test_proxy_not_written_when_none(tmp_config):
    cfg = TrawlerConfig(proxy=None)
    cfg.save()
    content = (tmp_config / "config.toml").read_text()
    assert "proxy" not in content


def test_rules_dir_not_written_when_none(tmp_config):
    cfg = TrawlerConfig(rules_dir=None)
    cfg.save()
    content = (tmp_config / "config.toml").read_text()
    assert "rules_dir" not in content


# ---------------------------------------------------------------------------
# LLM config
# ---------------------------------------------------------------------------

def test_llm_defaults(tmp_config):
    cfg = TrawlerConfig.load()
    assert cfg.llm_model is None
    assert cfg.llm_backend == "mlx"
    assert cfg.llm_context_tokens == 2048
    assert cfg.llm_remote_url is None
    assert cfg.llm_remote_api_key is None
    assert cfg.llm_system_prompt is None


def test_llm_roundtrip(tmp_config):
    cfg = TrawlerConfig(
        llm_model="mlx-community/Mistral-7B-Instruct-v0.2-4bit",
        llm_backend="mlx",
        llm_context_tokens=4096,
        llm_remote_url=None,
        llm_remote_api_key=None,
        llm_system_prompt="Be concise.",
    )
    cfg.save()
    loaded = TrawlerConfig.load()
    assert loaded.llm_model == "mlx-community/Mistral-7B-Instruct-v0.2-4bit"
    assert loaded.llm_backend == "mlx"
    assert loaded.llm_context_tokens == 4096
    assert loaded.llm_system_prompt == "Be concise."


def test_llm_remote_roundtrip(tmp_config):
    cfg = TrawlerConfig(
        llm_backend="remote",
        llm_model="mistral",
        llm_remote_url="http://localhost:11434/v1",
        llm_remote_api_key="sk-test",
    )
    cfg.save()
    loaded = TrawlerConfig.load()
    assert loaded.llm_backend == "remote"
    assert loaded.llm_model == "mistral"
    assert loaded.llm_remote_url == "http://localhost:11434/v1"
    assert loaded.llm_remote_api_key == "sk-test"


def test_llm_not_written_when_none(tmp_config):
    cfg = TrawlerConfig()
    cfg.save()
    content = (tmp_config / "config.toml").read_text()
    assert "llm_model" not in content
    assert "llm_remote_url" not in content
    assert "llm_remote_api_key" not in content
    assert "llm_system_prompt" not in content


def test_llm_system_prompt_none_roundtrip(tmp_config):
    cfg = TrawlerConfig(llm_system_prompt=None)
    cfg.save()
    loaded = TrawlerConfig.load()
    assert loaded.llm_system_prompt is None


def test_llm_context_tokens_roundtrip(tmp_config):
    cfg = TrawlerConfig(llm_context_tokens=8192)
    cfg.save()
    loaded = TrawlerConfig.load()
    assert loaded.llm_context_tokens == 8192
