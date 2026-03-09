"""Semantic search backend.

Uses LangChain + ChromaDB for vector storage with metadata filtering,
and sentence-transformers (HuggingFace) for local embeddings.

Storage: .trawler/chroma/  (persisted ChromaDB collection)
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterator

from rich.markup import escape

# Suppress noisy logs from transformers / huggingface_hub
for _logger in ("transformers", "sentence_transformers", "huggingface_hub", "chromadb"):
    logging.getLogger(_logger).setLevel(logging.ERROR)

CHROMA_DIR = Path.cwd() / ".trawler" / "chroma"
COLLECTION_NAME = "trawler"
DEFAULT_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
TOP_K = 8
MIN_SCORE = 0.1
EMBED_BATCH_SIZE = 64   # chunks per model inference call
FILE_BATCH_SIZE = 10    # files to read/embed/store per progress tick
READ_WORKERS = 32        # parallel file readers
CHROMA_MAX_BATCH = 5000  # ChromaDB hard limit is 5461; stay safely under

_embeddings_cache: dict[str, object] = {}


def _get_device() -> str:
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def _get_embeddings(model_name: str, device: str | None = None):
    if device is None:
        device = _get_device()
    cache_key = f"{model_name}:{device}"
    if cache_key not in _embeddings_cache:
        from langchain_huggingface import HuggingFaceEmbeddings
        _embeddings_cache[cache_key] = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": device},
            encode_kwargs={"batch_size": EMBED_BATCH_SIZE},
        )
    return _embeddings_cache[cache_key]


def _get_vectorstore(embeddings):
    from langchain_chroma import Chroma
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
        collection_metadata={"hnsw:space": "cosine"},
    )


def _delete_file_chunks(vectorstore, file_path: Path) -> None:
    """Remove all previously indexed chunks for a file (for re-indexing)."""
    try:
        vectorstore._collection.delete(where={"source": str(file_path)})
    except Exception:
        pass


def index(
    directories: list[str],
    model_name: str = DEFAULT_MODEL,
    emit: Callable[[str], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    stop_event: threading.Event | None = None,
    max_file_bytes: int = 0,
    index_extensions: list[str] | None = None,
) -> None:
    """Embed and store all new/changed files into ChromaDB."""
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from ..index_state import IndexState

    def log(msg: str) -> None:
        if emit:
            emit(msg)

    device = _get_device()
    log(f"[bold]Loading embedding model…[/] [dim](device: {device})[/]")
    try:
        embeddings = _get_embeddings(model_name, device)
        vectorstore = _get_vectorstore(embeddings)
    except Exception as e:
        log(f"[red]Failed to initialise embeddings/vectorstore:[/] {escape(str(e))}")
        for line in traceback.format_exc().splitlines():
            log(f"[dim]{escape(line)}[/]")
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    state = IndexState()
    unindexed = list(state.unindexed_files(directories))

    if not unindexed:
        log("[green]All files are already indexed.[/]")
        return

    def read_and_chunk(file_path: Path) -> tuple[Path, list[str] | None, str | None]:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            return file_path, splitter.split_text(text), None
        except (PermissionError, OSError) as e:
            return file_path, None, str(e)

    if max_file_bytes:
        skipped_size = [f for f in unindexed if f.stat().st_size > max_file_bytes]
        unindexed = [f for f in unindexed if f.stat().st_size <= max_file_bytes]
        if skipped_size:
            limit_kb = max_file_bytes // 1024
            log(
                f"[dim]Skipping {len(skipped_size)} file(s) over {limit_kb} KB limit.[/]"
            )

    if index_extensions:
        ext_set = set(index_extensions)
        type_skipped = [f for f in unindexed if f.suffix.lower() not in ext_set]
        unindexed = [f for f in unindexed if f.suffix.lower() in ext_set]
        if type_skipped:
            log(f"[dim]Skipping {len(type_skipped)} file(s) with non-indexed extensions.[/]")

    total = len(unindexed)
    if not total:
        log("[green]All eligible files are already indexed.[/]")
        return
    log(f"[bold]Indexing {total} file(s)…[/] [dim](batches of {FILE_BATCH_SIZE})[/]")

    indexed_count = 0
    errors = 0
    total_start = time.perf_counter()

    # Process in file-sized batches: read in parallel → embed → store → log progress
    for batch_start in range(0, total, FILE_BATCH_SIZE):
        if stop_event and stop_event.is_set():
            log("[yellow]Index stopped.[/]")
            break
        batch_t = time.perf_counter()
        file_batch = unindexed[batch_start:batch_start + FILE_BATCH_SIZE]
        batch_docs: list[Document] = []
        batch_files: list[Path] = []

        with ThreadPoolExecutor(max_workers=READ_WORKERS) as pool:
            futures = {pool.submit(read_and_chunk, fp): fp for fp in file_batch}
            for future in as_completed(futures):
                file_path, chunks, error = future.result()
                if error:
                    log(f"  [red]skip[/] {escape(str(file_path))}: {escape(error)}")
                    errors += 1
                    continue
                if not chunks:
                    state.mark_indexed(file_path)
                    continue

                _delete_file_chunks(vectorstore, file_path)
                config_dir = next(
                    (d for d in directories if str(file_path).startswith(d)),
                    str(file_path.parent),
                )
                for i, chunk in enumerate(chunks):
                    batch_docs.append(Document(
                        page_content=chunk,
                        metadata={"source": str(file_path), "config_dir": config_dir, "chunk": i},
                    ))
                batch_files.append(file_path)

        if batch_docs:
            try:
                for sub_start in range(0, len(batch_docs), CHROMA_MAX_BATCH):
                    vectorstore.add_documents(batch_docs[sub_start:sub_start + CHROMA_MAX_BATCH])
            except Exception as e:
                log(f"  [red]embed error:[/] {escape(str(e))}")
                errors += 1
                continue

        for fp in batch_files:
            state.mark_indexed(fp)
        indexed_count += len(batch_files)

        done = min(batch_start + FILE_BATCH_SIZE, total)
        pct = int(done / total * 100)
        batch_elapsed = time.perf_counter() - batch_t
        log(
            f"  [dim]{done}/{total} files ({pct}%) — "
            f"{len(batch_docs)} chunks — {batch_elapsed:.1f}s[/]"
        )

        if on_progress:
            on_progress(done, total)

    total_elapsed = time.perf_counter() - total_start
    minutes, secs = divmod(int(total_elapsed), 60)
    time_str = f"{minutes}m {secs}s" if minutes else f"{secs}s"
    log("")
    log(f"[bold green]Done.[/] {indexed_count} file(s) indexed, {errors} error(s) — {time_str} total")


def search(
    query: str,
    model_name: str = DEFAULT_MODEL,
    filter_dir: str | None = None,
) -> Iterator[str]:
    """Semantic similarity search."""
    if not CHROMA_DIR.exists():
        yield "[yellow]No index found.[/] Run [cyan]/index[/] first to build the vector index."
        return

    try:
        embeddings = _get_embeddings(model_name)
        vectorstore = _get_vectorstore(embeddings)
    except Exception as e:
        yield f"[red]Failed to load index:[/] {escape(str(e))}"
        return

    where: dict | None = {"config_dir": filter_dir} if filter_dir else None

    try:
        raw_results = vectorstore.similarity_search_with_score(
            query, k=TOP_K, filter=where
        )
    except Exception as e:
        yield f"[red]Search error:[/] {escape(str(e))}"
        return

    if not raw_results:
        suffix = f" in [cyan]{escape(filter_dir)}[/]" if filter_dir else ""
        yield f"[dim]No semantic matches found for:[/] {escape(query)}{suffix}"
        return

    found = False
    for doc, distance in raw_results:
        similarity = max(0.0, 1.0 - float(distance))
        if similarity < MIN_SCORE:
            continue
        found = True
        source = doc.metadata.get("source", "unknown")
        chunk_idx = doc.metadata.get("chunk", 0)
        pct = int(similarity * 100)
        preview = escape(doc.page_content[:300].replace("\n", " "))
        color = "green" if similarity > 0.5 else "yellow"
        yield (
            f"[cyan]{escape(source)}[/] "
            f"[dim]chunk {chunk_idx}[/] "
            f"[{color}]{pct}% match[/]"
        )
        yield f"  {preview}"
        yield ""

    if not found:
        yield f"[dim]No semantic matches above threshold for:[/] {escape(query)}"
