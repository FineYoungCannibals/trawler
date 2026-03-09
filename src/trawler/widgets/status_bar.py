from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__("[dim]Ready[/]", markup=True)

    def set_running(self, command: str) -> None:
        self.update(f"[yellow]●[/] {command}…")

    def set_done(self, summary: str) -> None:
        self.update(f"[green]✓[/] {summary}")
        self.set_timer(4, self._reset)

    def set_error(self, msg: str) -> None:
        self.update(f"[red]✗[/] {msg}")
        self.set_timer(4, self._reset)

    def set_info(self, msg: str) -> None:
        self.update(f"[dim]{msg}[/]")
        self.set_timer(4, self._reset)

    def set_hint(self, msg: str) -> None:
        """Persistent hint — no auto-reset."""
        self.update(f"[dim]{msg}[/]")

    def _reset(self) -> None:
        self.update("[dim]Ready[/]")
