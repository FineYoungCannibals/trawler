from __future__ import annotations

import fnmatch
import re
import threading
from pathlib import Path
from typing import Callable, Iterator

import yara
from rich.markup import escape

# Matches ANSI/VT escape sequences (CSI, OSC, etc.)
_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;]*[a-zA-Z]|\][^\x07]*(?:\x07|\x1b\\)|[^[\]]?)")

_MAX_MATCH_DISPLAY = 200  # characters
_MAX_LINE_DISPLAY = 300   # characters for context lines
_PROGRESS_INTERVAL = 100  # files between progress callbacks
_BINARY_THRESHOLD = 0.10  # fraction of replacement chars that signals binary


def _safe_text(text: str, max_len: int = _MAX_MATCH_DISPLAY) -> str:
    """Sanitise a decoded string for terminal-safe Rich display."""
    text = _ANSI_RE.sub("", text)                         # strip ANSI/VT sequences
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)    # strip remaining control chars
    if len(text) > max_len:
        text = text[:max_len] + "…"
    return escape(text)


def _safe_value(data: bytes) -> str:
    """Decode matched bytes to a terminal-safe display string."""
    return _safe_text(data.decode("utf-8", errors="replace"))


def _get_line_context(file_bytes: bytes, offset: int) -> tuple[int, str] | None:
    """Return (line_number, line_text) for the line containing *offset*.

    Returns ``None`` if the surrounding content looks binary (high ratio of
    replacement characters after UTF-8 decoding).
    """
    # Find line boundaries around offset
    line_start = file_bytes.rfind(b"\n", 0, offset) + 1  # 0 if no newline found
    line_end = file_bytes.find(b"\n", offset)
    if line_end == -1:
        line_end = len(file_bytes)

    line_bytes = file_bytes[line_start:line_end]
    decoded = line_bytes.decode("utf-8", errors="replace")

    # Heuristic: if too many replacement chars, it's binary
    if len(decoded) > 0:
        replacement_ratio = decoded.count("\ufffd") / len(decoded)
        if replacement_ratio > _BINARY_THRESHOLD:
            return None

    line_number = file_bytes[:offset].count(b"\n") + 1
    safe_line = _safe_text(decoded.strip(), max_len=_MAX_LINE_DISPLAY)
    return (line_number, safe_line)

DEFAULT_RULES_DIR = Path(__file__).parent.parent / "rules"


def _resolve_rules_dir(rules_dir: str | None) -> Path:
    return Path(rules_dir) if rules_dir else DEFAULT_RULES_DIR


def _load_all_rules(rules_dir: Path) -> yara.Rules | None:
    """Compile all YARA rules from the given rules directory."""
    rule_files = list(rules_dir.glob("*.yar")) + list(rules_dir.glob("*.yara"))
    if not rule_files:
        return None
    filepaths = {f.stem: str(f) for f in rule_files}
    return yara.compile(filepaths=filepaths)


def scan(
    pattern: str | None,
    directories: list[str],
    rules_dir: str | None = None,
    stop_event: threading.Event | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> Iterator[str]:
    """Run YARA rules against all files in configured directories.

    pattern:     glob to filter by rule name (None or '*' = all rules).
    rules_dir:   path to rules directory; defaults to the bundled rules/
    stop_event:  set to cancel the scan between files.
    on_progress: called every _PROGRESS_INTERVAL files with files_scanned count.
    """
    if not directories:
        yield "[yellow]No directories configured. Use /config to add one.[/]"
        return

    rdir = _resolve_rules_dir(rules_dir)
    rule_files = list(rdir.glob("*.yar")) + list(rdir.glob("*.yara"))
    if not rule_files:
        yield f"[yellow]No YARA rules found in:[/] {escape(str(rdir))}"
        return

    try:
        rules = _load_all_rules(rdir)
    except yara.SyntaxError as e:
        yield f"[red]YARA syntax error:[/] {escape(str(e))}"
        return

    if rules is None:
        yield "[yellow]No YARA rules loaded.[/]"
        return

    # Normalise pattern: None or '*' means match everything
    name_filter = pattern.strip() if pattern and pattern.strip() not in ("", "*") else None
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
                matches = rules.match(str(file_path))
                # Read file bytes once for line-context lookups
                file_bytes: bytes | None = None
                if matches:
                    try:
                        file_bytes = file_path.read_bytes()
                    except (PermissionError, OSError):
                        pass
                for match in matches:
                    # Filter by rule name glob if pattern given
                    if name_filter and not fnmatch.fnmatch(match.rule, name_filter):
                        continue
                    found_any = True
                    rel = escape(str(file_path))
                    rule_name = escape(match.rule)
                    yield f"[bold red][YARA][/] [yellow]{rule_name}[/] matched [cyan]{rel}[/]"
                    for string_match in match.strings:
                        if not string_match.instances:
                            continue
                        offset = string_match.instances[0].offset
                        identifier = escape(string_match.identifier)
                        try:
                            value = _safe_value(string_match.instances[0].matched_data)
                        except Exception:
                            value = "[dim][binary data][/]"

                        # Try to resolve line context for text files
                        ctx = None
                        if file_bytes is not None:
                            try:
                                ctx = _get_line_context(file_bytes, offset)
                            except Exception:
                                pass

                        if ctx is not None:
                            lineno, line_text = ctx
                            yield f"  [dim]line {lineno}[/] {identifier}: {value}"
                            yield f"    {line_text}"
                        else:
                            yield f"  [dim]offset {offset}[/] {identifier}: {value}"
            except (PermissionError, OSError, yara.Error):
                pass
            files_scanned += 1
            if on_progress and files_scanned % _PROGRESS_INTERVAL == 0:
                on_progress(files_scanned)

    if not found_any:
        if name_filter:
            yield f"[dim]No matches for rule pattern:[/] {escape(name_filter)}"
        else:
            yield "[dim]No YARA matches found.[/]"
