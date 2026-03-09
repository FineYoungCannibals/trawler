# Trawler

### A terminal TUI for triaging data dumps — drop files in a directory, search them fast, escalate what matters.

Trawler gives you a keyboard-driven interface to run regex, ripgrep, YARA, and semantic vector searches across breach data, leaks, and other unstructured dumps — without standing up any infrastructure.

---

## Features

- **Regex search** — line-by-line pattern matching across all files
- **Ripgrep** — fast full-text search with ripgrep flags
- **YARA rules** — scan files against rules in `src/trawler/rules/`
- **Semantic search** — vector similarity search via ChromaDB + sentence-transformers (local, no API key)
- **Incremental indexing** — only re-embeds files that have changed since the last run
- **File type & size filtering** — skip binary, structured, or oversized files before indexing
- **Tab path completion** — complete directory paths directly in the command bar
- **Clipboard export** — `ctrl+y` copies all results to clipboard

---

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv)
- macOS / Linux (clipboard export uses `pbcopy` on macOS)

---

## Installation

```bash
git clone https://github.com/FineYoungCannibals/trawler
cd trawler
uv sync
```

---

## Running

```bash
uv run python main.py
```

> `uv run` automatically uses the project's virtual environment — no activation needed. If you prefer an active shell, run `uv shell` first.

---

## Commands

| Command | Description |
|---------|-------------|
| `/search <pattern>` | Regex search across all configured directories |
| `/rg [opts] <pattern>` | Ripgrep search (supports `-i`, `-m` flags) |
| `/yara [rule-glob]` | Run YARA rules; glob filters by rule name (e.g. `email*`) |
| `/semantic <query> [--dir <path>]` | Vector similarity search; `--dir` filters to one directory |
| `/index` | Embed and index configured directories into ChromaDB |
| `/config [subcommand]` | Manage configuration — run with no args to see all options |
| `/reset` | Wipe the vector store and indexing history (requires confirmation) |
| `/help` | Show command reference |
| `/exit` | Quit |

### Config subcommands

```
/config                        show full configuration summary
/config add <path>             add a watched directory (Tab completes the path)
/config rm <path>              remove a watched directory
/config filesize <value>       set max file size for indexing (e.g. 500KB, 2MB, 0=unlimited)
/config ext list               show extension whitelist and skiplist
/config ext add <.ext>         whitelist an extension for indexing
/config ext rm <.ext>          move an extension to the skiplist
/config ext reset              reset extensions to defaults
```

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Tab` | Accept autocomplete suggestion |
| `ctrl+y` | Copy results to clipboard |
| `ctrl+c` | Quit (or cancel indexing if running) |
| `Enter` (empty input) | Return to home screen |

---

## Configuration

Config is stored at `.trawler/config.toml` relative to your working directory. All data (config, index state, vector store) is project-local and gitignored.

**File size limit** — the first time you run `/index`, you'll be prompted to set a maximum file size. Large files slow down embedding significantly. 500 KB is a reasonable default for text content.

**Extension whitelist** — on first index, any file types not already known will trigger a prompt asking whether to include them. You can adjust the whitelist at any time with `/config ext add/rm`.

### Default indexed extensions

`.txt` `.md` `.rst` `.text` `.html` `.htm` `.eml` `.mbox` `.log`

### Default skipped extensions

Binary, structured data, archives, images, audio, video — everything that won't yield useful semantic content.

---

## YARA Rules

Place `.yar` or `.yara` files in `src/trawler/rules/`. All rules are compiled and run on every `/yara` invocation.

An example rule is included at `src/trawler/rules/example.yar` covering email addresses and credential patterns.

```yara
rule email_address {
    strings:
        $email = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/
    condition:
        $email
}
```

Filter by rule name using a glob: `/yara email*` runs only rules whose name starts with `email`.

---

## Semantic Search

Semantic search uses [sentence-transformers](https://www.sbert.net/) to embed file content locally and stores vectors in ChromaDB. No data leaves your machine.

**Model**: `all-MiniLM-L6-v2` by default (fast, ~80 MB). Change with `/config` → edit `embedding_model` in `.trawler/config.toml`.

**Device**: MPS (Apple Silicon) → CUDA → CPU, auto-detected.

**When to use it**: semantic search is best for natural language content (emails, logs, notes). It is not well-suited for structured data (JSON, CSV, SQL) — use `/rg` for those.

**Indexing**: run `/index` to embed your directories. Re-running is incremental — only changed files are re-embedded. Indexing large directories will take time on first run; subsequent runs are fast.

---

## Development

```bash
# Install deps (including dev)
uv sync

# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_config.py::test_save_load_roundtrip

# Launch the TUI
uv run python main.py
```

---

## Architecture

```
src/trawler/
├── app.py              # TrawlerApp — main Textual application
├── config.py           # TrawlerConfig — TOML-backed settings
├── index_state.py      # IndexState — tracks which files are embedded
├── rules/              # YARA rule files (.yar / .yara)
├── search/
│   ├── basic.py        # Regex line search
│   ├── ripgrep.py      # python-ripgrep wrapper
│   ├── yara_scan.py    # YARA scanning backend
│   └── semantic.py     # LangChain + ChromaDB vector search
└── widgets/
    ├── command_bar.py  # Input widget with command + path autocomplete
    ├── results_panel.py# RichLog results display
    ├── sidebar.py      # Directory list with indexing stats
    └── status_bar.py   # Single-line status indicator
```

Project-local data lives in `.trawler/` (gitignored):

```
.trawler/
├── config.toml         # Settings
├── index_state.json    # Per-file mtime + size records
└── chroma/             # ChromaDB vector store
```
