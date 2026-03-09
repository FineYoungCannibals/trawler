from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from rich.markup import escape


def search(pattern: str, directories: list[str]) -> Iterator[str]:
    """Line-by-line regex/literal search across all files in configured directories."""
    if not directories:
        yield "[yellow]No directories configured. Use /config to add one.[/]"
        return

    try:
        regex = re.compile(pattern)
    except re.error:
        regex = re.compile(re.escape(pattern))

    found_any = False
    for dir_path in directories:
        p = Path(dir_path)
        if not p.is_dir():
            yield f"[red]Not a directory:[/] {escape(dir_path)}"
            continue
        for file_path in p.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if regex.search(line):
                            found_any = True
                            content = escape(line.rstrip())
                            rel = escape(str(file_path))
                            yield f"[cyan]{rel}[/]:[yellow]{lineno}[/]: {content}"
            except (PermissionError, OSError):
                continue

    if not found_any:
        yield f"[dim]No matches found for:[/] {escape(pattern)}"
