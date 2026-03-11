from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Iterator

import yara
from rich.markup import escape

# Matches ANSI/VT escape sequences (CSI, OSC, etc.)
_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;]*[a-zA-Z]|\][^\x07]*(?:\x07|\x1b\\)|[^[\]]?)")

_MAX_MATCH_DISPLAY = 200  # characters


def _safe_value(data: bytes) -> str:
    """Decode matched bytes to a terminal-safe display string."""
    text = data.decode("utf-8", errors="replace")
    text = _ANSI_RE.sub("", text)                         # strip ANSI/VT sequences
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)    # strip remaining control chars
    if len(text) > _MAX_MATCH_DISPLAY:
        text = text[:_MAX_MATCH_DISPLAY] + "…"
    return escape(text)

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


def scan(pattern: str | None, directories: list[str], rules_dir: str | None = None) -> Iterator[str]:
    """Run YARA rules against all files in configured directories.

    pattern:   glob to filter by rule name (None or '*' = all rules).
    rules_dir: path to rules directory; defaults to the bundled rules/
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

    for dir_path in directories:
        p = Path(dir_path)
        if not p.is_dir():
            yield f"[red]Not a directory:[/] {escape(dir_path)}"
            continue
        for file_path in p.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                matches = rules.match(str(file_path))
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
                        yield f"  [dim]offset {offset}[/] {identifier}: {value}"
            except (PermissionError, OSError, yara.Error):
                continue

    if not found_any:
        if name_filter:
            yield f"[dim]No matches for rule pattern:[/] {escape(name_filter)}"
        else:
            yield "[dim]No YARA matches found.[/]"
