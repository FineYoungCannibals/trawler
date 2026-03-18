"""Tests for OAuth 2.0 token fetch and header merge in _ask_remote."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from trawler.search import local_llm
from trawler.search.local_llm import _fetch_oauth_token


# ---------------------------------------------------------------------------
# Minimal config stub (avoids importing the real TrawlerConfig)
# ---------------------------------------------------------------------------

@dataclass
class _FakeConfig:
    llm_remote_url: str = "http://llm.test:8080"
    llm_remote_api_key: str | None = None
    llm_model: str | None = "test-model"
    llm_context_tokens: int = 2048
    llm_system_prompt: str | None = None
    llm_backend: str = "remote"
    llm_remote_headers: dict[str, str] = field(default_factory=dict)
    llm_oauth: dict[str, str] | None = None
    proxy: str | None = None


# ---------------------------------------------------------------------------
# _fetch_oauth_token
# ---------------------------------------------------------------------------

class TestFetchOAuthToken:
    """Tests for the OAuth client-credentials token fetch helper."""

    def setup_method(self):
        # Clear cache between tests
        local_llm._oauth_cache.clear()

    def test_fetches_token_successfully(self):
        oauth_cfg = {
            "auth_url": "https://auth.test/token",
            "client_id": "cid",
            "client_secret": "csecret",
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "tok123", "expires_in": 3600}

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.return_value = mock_resp

            token = _fetch_oauth_token(oauth_cfg)

        assert token == "tok123"
        MockClient.return_value.post.assert_called_once_with(
            "https://auth.test/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "cid",
                "client_secret": "csecret",
            },
        )

    def test_includes_scope_when_provided(self):
        oauth_cfg = {
            "auth_url": "https://auth.test/token",
            "client_id": "cid",
            "client_secret": "csecret",
            "scope": "llm.access",
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "tok_s", "expires_in": 3600}

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.return_value = mock_resp

            _fetch_oauth_token(oauth_cfg)

        call_data = MockClient.return_value.post.call_args[1]["data"]
        assert call_data["scope"] == "llm.access"

    def test_returns_cached_token_when_valid(self):
        local_llm._oauth_cache["access_token"] = "cached_tok"
        local_llm._oauth_cache["expires_at"] = time.monotonic() + 600

        # Should not make any HTTP call
        token = _fetch_oauth_token({"auth_url": "x", "client_id": "x", "client_secret": "x"})
        assert token == "cached_tok"

    def test_refetches_when_cache_expired(self):
        local_llm._oauth_cache["access_token"] = "old"
        local_llm._oauth_cache["expires_at"] = time.monotonic() - 10  # expired

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "new_tok", "expires_in": 1800}

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.return_value = mock_resp

            token = _fetch_oauth_token({"auth_url": "https://a", "client_id": "c", "client_secret": "s"})

        assert token == "new_tok"

    def test_raises_on_http_error(self):
        import httpx

        oauth_cfg = {"auth_url": "https://auth.test/token", "client_id": "c", "client_secret": "s"}
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401", request=MagicMock(), response=MagicMock()
        )

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.return_value = mock_resp

            with pytest.raises(httpx.HTTPStatusError):
                _fetch_oauth_token(oauth_cfg)

    def test_passes_proxy_to_client(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "t", "expires_in": 60}

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.return_value = mock_resp

            _fetch_oauth_token(
                {"auth_url": "https://a", "client_id": "c", "client_secret": "s"},
                proxy="http://proxy:8080",
            )

        MockClient.assert_called_once_with(timeout=10, proxy="http://proxy:8080")


# ---------------------------------------------------------------------------
# Header merge in _ask_remote
# ---------------------------------------------------------------------------

def _collect_headers_from_ask_remote(config):
    """Run _ask_remote with a mocked httpx.Client and return the headers dict used."""
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass
        def iter_lines(self):
            yield "data: [DONE]"
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    class FakeClient:
        def __init__(self, **kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def stream(self, method, url, json=None, headers=None):
            captured["headers"] = dict(headers) if headers else {}
            return FakeResponse()

    with patch("httpx.Client", FakeClient):
        tokens = list(local_llm._ask_remote("q", "ctx", config))

    return captured.get("headers", {}), tokens


class TestHeaderMerge:
    """Verify header priority: llm_remote_headers > oauth/api_key > Content-Type."""

    def setup_method(self):
        local_llm._oauth_cache.clear()

    def test_default_headers_only(self):
        cfg = _FakeConfig()
        headers, _ = _collect_headers_from_ask_remote(cfg)
        assert headers["Content-Type"] == "application/json"
        assert "Authorization" not in headers

    def test_api_key_sets_bearer(self):
        cfg = _FakeConfig(llm_remote_api_key="sk-123")
        headers, _ = _collect_headers_from_ask_remote(cfg)
        assert headers["Authorization"] == "Bearer sk-123"

    def test_custom_headers_merged(self):
        cfg = _FakeConfig(llm_remote_headers={"X-Custom": "val", "X-Other": "v2"})
        headers, _ = _collect_headers_from_ask_remote(cfg)
        assert headers["X-Custom"] == "val"
        assert headers["X-Other"] == "v2"
        assert headers["Content-Type"] == "application/json"

    def test_custom_headers_override_content_type(self):
        cfg = _FakeConfig(llm_remote_headers={"Content-Type": "text/plain"})
        headers, _ = _collect_headers_from_ask_remote(cfg)
        assert headers["Content-Type"] == "text/plain"

    def test_oauth_overrides_api_key(self):
        cfg = _FakeConfig(
            llm_remote_api_key="sk-should-not-use",
            llm_oauth={"auth_url": "https://a", "client_id": "c", "client_secret": "s"},
        )

        with patch("trawler.search.local_llm._fetch_oauth_token", return_value="oauth_tok"):
            headers, _ = _collect_headers_from_ask_remote(cfg)

        assert headers["Authorization"] == "Bearer oauth_tok"

    def test_custom_headers_override_oauth_auth(self):
        cfg = _FakeConfig(
            llm_oauth={"auth_url": "https://a", "client_id": "c", "client_secret": "s"},
            llm_remote_headers={"Authorization": "Custom xyz"},
        )

        with patch("trawler.search.local_llm._fetch_oauth_token", return_value="oauth_tok"):
            headers, _ = _collect_headers_from_ask_remote(cfg)

        # Custom header should win over OAuth
        assert headers["Authorization"] == "Custom xyz"

    def test_oauth_failure_yields_error(self):
        cfg = _FakeConfig(
            llm_oauth={"auth_url": "https://a", "client_id": "c", "client_secret": "s"},
        )

        with patch("trawler.search.local_llm._fetch_oauth_token", side_effect=RuntimeError("conn refused")):
            headers, tokens = _collect_headers_from_ask_remote(cfg)

        assert any("OAuth token fetch failed" in t for t in tokens)
