from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Callable, Iterator

from rich.markup import escape

from .extract import EXTRACTABLE_EXTENSIONS, extract_text

_PROGRESS_INTERVAL = 100   # update status bar every N files scanned


def search(
    pattern: str,
    directories: list[str],
    stop_event: threading.Event | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> Iterator[str]:
    """Line-by-line regex/literal search across all files in configured directories.

    PDF and DOCX files are text-extracted before searching; all other files
    are read as UTF-8.  /rg does not support PDF/DOCX (ripgrep treats them as
    binary) — use /search or /semantic for document content.

    Args:
        stop_event: when set, the search stops cleanly after the current file.
        on_progress: called every _PROGRESS_INTERVAL files with the count so far.
    """
    if not directories:
        yield "[yellow]No directories configured. Use /config to add one.[/]"
        return

    try:
        regex = re.compile(pattern)
    except re.error:
        regex = re.compile(re.escape(pattern))

    found_any = False
    files_scanned = 0

    for dir_path in directories:
        p = Path(dir_path)
        if not p.is_dir():
            yield f"[red]Not a directory:[/] {escape(dir_path)}"
            continue
        for file_path in p.rglob("*"):
            if stop_event and stop_event.is_set():
                return
            if not file_path.is_file():
                continue
            try:
                if file_path.suffix.lower() in EXTRACTABLE_EXTENSIONS:
                    text = extract_text(file_path)
                    lines = text.splitlines()
                    for lineno, line in enumerate(lines, 1):
                        if regex.search(line):
                            found_any = True
                            yield (
                                f"[cyan]{escape(str(file_path))}[/]"
                                f":[yellow]{lineno}[/]: {escape(line.rstrip())}"
                            )
                else:
                    with open(file_path, encoding="utf-8", errors="replace") as f:
                        for lineno, line in enumerate(f, 1):
                            if regex.search(line):
                                found_any = True
                                content = escape(line.rstrip())
                                rel = escape(str(file_path))
                                yield f"[cyan]{rel}[/]:[yellow]{lineno}[/]: {content}"
            except (PermissionError, OSError):
                continue
            finally:
                files_scanned += 1
                if on_progress and files_scanned % _PROGRESS_INTERVAL == 0:
                    on_progress(files_scanned)

    if not found_any:
        yield f"[dim]No matches found for:[/] {escape(pattern)}"
