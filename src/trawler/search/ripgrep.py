from __future__ import annotations

import shlex
from typing import Iterator

from rich.markup import escape

from python_ripgrep import search as _rg_search


def search(args_str: str, directories: list[str]) -> Iterator[str]:
    """Run ripgrep via python_ripgrep. args_str is everything after /rg."""
    if not directories:
        yield "[yellow]No directories configured. Use /config to add one.[/]"
        return

    parts = shlex.split(args_str) if args_str.strip() else []
    if not parts:
        yield "[red]Usage:[/] /rg [options] <pattern>"
        return

    # Separate flags from the pattern (pattern is last non-flag token)
    # For python_ripgrep's API, only pattern and paths are supported directly.
    # We treat the last token as the pattern.
    pattern = parts[-1]

    # Map a subset of common flags to python_ripgrep kwargs
    kwargs: dict = {
        "patterns": [pattern],
        "paths": directories,
        "line_number": True,
    }

    # Parse simple flags we can honor
    flags = parts[:-1]
    for flag in flags:
        if flag in ("-i", "--ignore-case"):
            # python_ripgrep doesn't expose case-insensitive directly;
            # prefix pattern with (?i) for case-insensitive matching
            kwargs["patterns"] = [f"(?i){pattern}"]
        elif flag in ("-m", "--multiline"):
            kwargs["multiline"] = True

    try:
        results = _rg_search(**kwargs)
    except Exception as e:
        yield f"[red]ripgrep error:[/] {escape(str(e))}"
        return

    if not results:
        yield f"[dim]No matches found for:[/] {escape(pattern)}"
        return

    for line in results:
        yield escape(line)
