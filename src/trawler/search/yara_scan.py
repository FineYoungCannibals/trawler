from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterator

import yara
from rich.markup import escape

RULES_DIR = Path(__file__).parent.parent / "rules"


def _load_all_rules() -> yara.Rules | None:
    """Compile all YARA rules from the rules directory."""
    rule_files = list(RULES_DIR.glob("*.yar")) + list(RULES_DIR.glob("*.yara"))
    if not rule_files:
        return None
    filepaths = {f.stem: str(f) for f in rule_files}
    return yara.compile(filepaths=filepaths)


def scan(pattern: str | None, directories: list[str]) -> Iterator[str]:
    """Run YARA rules against all files in configured directories.

    pattern: glob to filter by rule name (None or '*' = all rules).
    """
    if not directories:
        yield "[yellow]No directories configured. Use /config to add one.[/]"
        return

    rule_files = list(RULES_DIR.glob("*.yar")) + list(RULES_DIR.glob("*.yara"))
    if not rule_files:
        yield f"[yellow]No YARA rules found in:[/] {escape(str(RULES_DIR))}"
        return

    try:
        rules = _load_all_rules()
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
                            value = escape(
                                string_match.instances[0].matched_data.decode(
                                    "utf-8", errors="replace"
                                )
                            )
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
