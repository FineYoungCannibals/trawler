"""Local and remote LLM backend for /ask command.

Supports three backends:
  mlx       — mlx-lm (Apple Silicon, in-process)
  llama-cpp — llama-cpp-python (cross-platform, in-process)
  remote    — any OpenAI-compatible HTTP endpoint (streaming SSE)
"""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Callable, Generator

if TYPE_CHECKING:
    from ..config import TrawlerConfig

# Module-level cache so the model is not reloaded between /ask calls
_llm_cache: dict[str, object] = {}

_BAR_WIDTH = 20
_BAR_FULL = "█"
_BAR_EMPTY = "░"


def _render_bar(n: int, total: int) -> str:
    pct = int(n / total * 100) if total else 0
    filled = pct * _BAR_WIDTH // 100
    bar = _BAR_FULL * filled + _BAR_EMPTY * (_BAR_WIDTH - filled)
    size_mb = total / (1024 * 1024)
    done_mb = n / (1024 * 1024)
    return f"[{bar}] {pct:3d}%  {done_mb:.1f}/{size_mb:.1f} MB"


def ensure_model_cached(
    model_id: str,
    on_progress: Callable[[str], None],
) -> tuple[bool, str | None]:
    """Pre-download an MLX model with per-file progress bars.

    Returns (True, None) if the model is ready (already cached or just downloaded).
    Returns (False, error_message) on failure.
    No-op if the snapshot is already fully cached.
    """
    try:
        import tqdm as tqdm_lib
        from huggingface_hub import snapshot_download, try_to_load_from_cache
        from huggingface_hub.utils import EntryNotFoundError  # noqa: F401
    except ImportError:
        return True, None  # can't check — let mlx_lm.load() handle it

    # If config.json is already cached the snapshot is complete enough to load.
    cached = try_to_load_from_cache(model_id, "config.json")
    if isinstance(cached, str):
        return True, None

    on_progress("[dim]Fetching model file list from HuggingFace Hub…[/]")

    file_progress: dict[str, tuple[int, int]] = {}
    last_emit = 0.0

    def _emit() -> None:
        nonlocal last_emit
        now = time.monotonic()
        if now - last_emit < 0.1:
            return
        last_emit = now
        lines = ["[bold]Downloading model from HuggingFace Hub[/]", ""]
        for fname, (n, total) in sorted(file_progress.items()):
            bar = _render_bar(n, total)
            short = fname.split("/")[-1] if "/" in fname else fname
            lines.append(f"  [dim]{short:<45}[/]  {bar}")
        on_progress("\n".join(lines))

    class _ProgressTqdm(tqdm_lib.tqdm):
        def __init__(self, *args, **kwargs) -> None:
            kwargs.pop("name", None)  # huggingface_hub passes this; tqdm rejects it
            super().__init__(*args, **kwargs)

        def update(self, n: int = 1) -> bool | None:  # type: ignore[override]
            result = super().update(n)
            desc = self.desc or ""
            total = self.total or 0
            if total > 0 and desc:
                file_progress[desc] = (int(self.n), int(total))
                _emit()
            return result

    try:
        snapshot_download(model_id, tqdm_class=_ProgressTqdm)
        return True, None
    except Exception as e:
        import traceback
        from rich.markup import escape
        detail = traceback.format_exc()
        return False, (
            f"[red]Download failed:[/] {escape(str(e))}\n"
            + "\n".join(f"[dim]{escape(l)}[/]" for l in detail.splitlines())
        )


def ask(
    question: str,
    context: str,
    config: TrawlerConfig,
) -> Generator[str, None, None]:
    """Stream response tokens from the configured LLM backend."""
    backend = config.llm_backend

    if backend == "remote":
        if not config.llm_remote_url:
            yield (
                "[yellow]No remote LLM URL configured.[/] "
                "Use [cyan]/config llm remote <url>[/] to set one."
            )
            return
        yield from _ask_remote(question, context, config)
    elif backend == "mlx":
        if not config.llm_model:
            yield (
                "[yellow]No LLM model configured.[/] "
                "Use [cyan]/config llm <model-id>[/] to set a local model."
            )
            return
        yield from _ask_mlx(question, context, config)
    elif backend == "llama-cpp":
        if not config.llm_model:
            yield (
                "[yellow]No LLM model configured.[/] "
                "Use [cyan]/config llm <model-id>[/] to set a local model."
            )
            return
        yield from _ask_llamacpp(question, context, config)
    else:
        yield f"[red]Unknown LLM backend:[/] {backend}"


def _truncate_context(context: str, max_tokens: int) -> str:
    """Rough token-budget trim: ~4 chars per token."""
    max_chars = max_tokens * 4
    if len(context) > max_chars:
        return context[:max_chars] + "\n[...truncated]"
    return context


def _build_messages(question: str, context: str, system_prompt: str | None) -> list[dict]:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({
        "role": "user",
        "content": f"Search results:\n\n{context}\n\nQuestion: {question}",
    })
    return messages


def _ask_mlx(
    question: str, context: str, config: TrawlerConfig
) -> Generator[str, None, None]:
    try:
        import mlx_lm
    except ImportError:
        yield (
            "[red]mlx-lm not installed.[/] "
            "Run [cyan]uv add --optional llm mlx-lm[/] or use "
            "[cyan]/config llm remote <url>[/] for remote inference."
        )
        return

    model_id = config.llm_model
    cache_key = f"mlx:{model_id}"
    if cache_key not in _llm_cache:
        yield f"[dim]Loading {model_id} into memory…[/]"
        try:
            model, tokenizer = mlx_lm.load(model_id)
            _llm_cache[cache_key] = (model, tokenizer)
        except Exception as e:
            from rich.markup import escape
            yield f"[red]Failed to load model:[/] {escape(str(e))}"
            return
    else:
        model, tokenizer = _llm_cache[cache_key]  # type: ignore[misc]

    ctx = _truncate_context(context, config.llm_context_tokens - 200)
    sys = f"{config.llm_system_prompt}\n\n" if config.llm_system_prompt else ""
    prompt = f"[INST] {sys}Search results:\n\n{ctx}\n\nQuestion: {question} [/INST]"
    try:
        response = mlx_lm.generate(model, tokenizer, prompt=prompt, verbose=False)
        yield response
    except Exception as e:
        from rich.markup import escape
        yield f"[red]LLM error:[/] {escape(str(e))}"


def _ask_llamacpp(
    question: str, context: str, config: TrawlerConfig
) -> Generator[str, None, None]:
    try:
        from llama_cpp import Llama
    except ImportError:
        yield (
            "[red]llama-cpp-python not installed.[/] "
            "Run [cyan]uv add --optional llm-cpu llama-cpp-python[/] or use "
            "[cyan]/config llm remote <url>[/]."
        )
        return

    model_id = config.llm_model
    cache_key = f"llama-cpp:{model_id}"
    if cache_key not in _llm_cache:
        yield f"[dim]Loading model {model_id}… (first load may take a minute)[/]"
        try:
            llm = Llama(
                model_path=model_id,
                n_ctx=config.llm_context_tokens,
                verbose=False,
            )
            _llm_cache[cache_key] = llm
        except Exception as e:
            from rich.markup import escape
            yield f"[red]Failed to load model:[/] {escape(str(e))}"
            return
    else:
        llm = _llm_cache[cache_key]  # type: ignore[assignment]

    ctx = _truncate_context(context, config.llm_context_tokens - 200)
    messages = _build_messages(question, ctx, config.llm_system_prompt)
    try:
        stream = llm.create_chat_completion(messages=messages, stream=True)
        for chunk in stream:
            delta = chunk["choices"][0]["delta"]
            if "content" in delta and delta["content"]:
                yield delta["content"]
    except Exception as e:
        from rich.markup import escape
        yield f"[red]LLM error:[/] {escape(str(e))}"


def _ask_remote(
    question: str, context: str, config: TrawlerConfig
) -> Generator[str, None, None]:
    import httpx
    from rich.markup import escape

    url = config.llm_remote_url.rstrip("/") + "/chat/completions"  # type: ignore[union-attr]
    ctx = _truncate_context(context, config.llm_context_tokens - 200)
    messages = _build_messages(question, ctx, config.llm_system_prompt)

    headers = {"Content-Type": "application/json"}
    if config.llm_remote_api_key:
        headers["Authorization"] = f"Bearer {config.llm_remote_api_key}"

    payload: dict = {"messages": messages, "stream": True}
    if config.llm_model:
        payload["model"] = config.llm_model

    try:
        client_kwargs: dict = {"timeout": 10}
        if config.proxy:
            client_kwargs["proxy"] = config.proxy
        with httpx.Client(**client_kwargs) as client:
            with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"]
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
    except httpx.HTTPStatusError as e:
        yield f"[red]HTTP {e.response.status_code}:[/] {escape(str(e))}"
    except Exception as e:
        yield f"[red]Remote LLM error:[/] {escape(str(e))}"
