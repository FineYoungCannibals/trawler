# Trawler

### A terminal TUI for triaging data dumps — drop files in a directory, search them fast, ask an LLM what it means.

Trawler gives you a keyboard-driven interface to run regex, ripgrep, YARA, and semantic vector searches across breach data, leaks, and other unstructured dumps — without standing up any infrastructure.

---

## Features

- **Regex search** — line-by-line pattern matching across all files
- **Ripgrep** — fast full-text search with full ripgrep flag support
- **YARA rules** — scan files against rules in `src/trawler/rules/`
- **Semantic search** — vector similarity search via ChromaDB + sentence-transformers (local, no API key)
- **LLM `/ask`** — ask a local or remote LLM questions about the current results panel; streams tokens as they arrive
- **Directory scoping** — add `--dir <path>` to any search command to restrict results to one directory
- **Incremental indexing** — only re-embeds files that have changed since the last run
- **File type & size filtering** — skip binary, structured, or oversized files before indexing
- **Progressive command help** — type any command or subcommand alone to see what's available at that level
- **Tab path completion** — complete directory paths in the command bar, including `--dir` arguments
- **Command history** — up/down arrows cycle through previous commands, shell-style
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

For local LLM support (optional):

```bash
uv sync --extra llm        # Apple Silicon (mlx-lm)
uv sync --extra llm-cpu    # cross-platform (llama-cpp-python)
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
| `/search <pattern> [--dir <path>]` | Regex search across all configured directories |
| `/rg [opts] <pattern> [--dir <path>]` | Ripgrep search (supports `-i`, `-m`, and all other rg flags) |
| `/yara [rule-glob] [--dir <path>]` | Run YARA rules; glob filters by rule name (e.g. `email*`) |
| `/semantic <query> [--dir <path>]` | Vector similarity search; `--dir` filters to one directory |
| `/index` | Embed and index configured directories into ChromaDB |
| `/ask <question>` | Ask a local or remote LLM about the current results panel |
| `/config [subcommand]` | Manage configuration — run with no args to see all options |
| `/reset` | Wipe the vector store and indexing history (requires confirmation) |
| `/help [command]` | Show help for a command or the full reference |
| `/exit` | Quit |

### Directory scoping

All four search commands accept an optional `--dir <path>` flag to restrict the search to a single directory. The path can be any directory on disk — not just a configured one, so you can drill into subdirectories freely.

```
/search password --dir /data/breach2/
/rg -i email --dir /data/drops/2024/
/yara email* --dir /data/breach2/
/semantic login credentials --dir /data/drops/
```

Typing `--dir ` and pressing Tab completes filesystem paths the same way `/config path add` does.

### Progressive help

Every command and subcommand shows its own help when typed alone:

```
/config          → shows config subcommands
/config ext      → shows ext subcommands
/config llm      → shows LLM config with current values
/help rg         → shows ripgrep usage
```

### Config subcommands

```
/config                               show full configuration summary
/config path                          manage watched directories
/config path add <path>               add a watched directory (Tab completes the path)
/config path rm <n|path>              remove a watched directory by number or full path
/config filesize <value>              set max file size for indexing (e.g. 500KB, 2MB, 0=unlimited)
/config ext                           manage file extension filters
/config ext list                      show extension whitelist and skiplist
/config ext add <.ext>                whitelist an extension for indexing
/config ext rm <.ext>                 move an extension to the skiplist
/config ext reset                     reset extensions to defaults
/config rules <path>                  set a custom YARA rules directory
/config rules reset                   revert to the bundled rules directory
/config proxy <url>                   set HTTP/HTTPS proxy
/config proxy reset                   clear proxy setting
/config llm                           view LLM configuration and available commands
/config llm mlx <hf-repo-id>          Apple Silicon local model (auto-downloaded)
/config llm gguf <path>               cross-platform local model (local .gguf file)
/config llm remote <url> [<model>]    remote OpenAI-compatible endpoint
/config llm apikey <key>              API key for remote endpoint
/config llm systemprompt <text>       set a system prompt (none by default)
/config llm systemprompt reset        remove system prompt
/config llm reset                     disable LLM
```

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Tab` | Accept autocomplete suggestion |
| `↑` / `↓` | Cycle through command history |
| `ctrl+y` | Copy results to clipboard |
| `ctrl+c` | Quit (or cancel indexing if running) |
| `Enter` (empty input) | Return to home screen |

### Selecting text in the results panel

Trawler captures mouse events for its TUI, so plain click-drag won't select text. Use the terminal's bypass modifier instead:

| Terminal | Gesture |
|----------|---------|
| macOS iTerm2 | `Cmd` + drag |
| macOS Terminal.app | `Option` + drag (or disable mouse reporting via View menu) |
| Windows Terminal | `Shift` + drag |
| Linux (most terminals) | `Shift` + drag, or middle-click to paste selection |

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

## LLM Integration (`/ask`)

`/ask` sends the current results panel as context to a local or remote LLM and streams the response back token-by-token. The command bar is disabled while the LLM is responding.

No system prompt is sent by default. The LLM sees only the question and your results as context, without any role-framing that might colour its answers.

### Option 1 — Apple Silicon (mlx-lm)

Models are downloaded automatically from HuggingFace on first use and cached in `~/.cache/huggingface/hub/`. Download progress is shown in-panel with per-file progress bars.

```
/config llm mlx mlx-community/Mistral-7B-Instruct-v0.2-4bit
```

Requires `uv sync --extra llm`. Apple Silicon only.

### Option 2 — Cross-platform (llama-cpp GGUF)

Point at a local `.gguf` file. You manage the download yourself.

```
/config llm gguf ~/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf
```

Get GGUF files from [huggingface.co/bartowski](https://huggingface.co/bartowski) or [huggingface.co/TheBloke](https://huggingface.co/TheBloke). Requires `uv sync --extra llm-cpu`.

### Option 3 — Remote endpoint (recommended for most setups)

Any OpenAI-compatible API — [Ollama](https://ollama.com), LM Studio, vLLM, llama.cpp server, or actual OpenAI.

```
/config llm remote http://localhost:11434/v1 mistral
/config llm apikey sk-...    # if required
```

No local model download, no extra dependencies. Tokens stream as they arrive from the remote host.

### System prompt

No system prompt is set by default. Add one if you want to constrain the model's behavior:

```
/config llm systemprompt You are a triage analyst. Answer only from the provided results.
/config llm systemprompt reset
```

### Memory requirements (4-bit quantized local models)

| Model size | RAM needed |
|------------|------------|
| 7B | ~4–5 GB |
| 13B | ~8–10 GB |
| 30B+ | 15+ GB |

---

## YARA Rules

By default, rules are loaded from `src/trawler/rules/` (bundled with the package). You can point trawler at your own rules directory with `/config rules <path>`, which persists across sessions. Run `/config rules reset` to revert to the default.

Place `.yar` or `.yara` files in your rules directory — all of them are compiled and run on every `/yara` invocation.

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

**Indexing**: run `/index` to embed your directories. Re-running is incremental — only changed files are re-embedded.

---

## Proxy Support

If you're behind a corporate proxy, set it once and it persists across sessions:

```
/config proxy http://proxy.corp.com:8080
/config proxy reset    # clear it
```

This sets `HTTP_PROXY` and `HTTPS_PROXY` in the running process, which is picked up by `requests`, `huggingface_hub`, `sentence-transformers`, and the remote LLM backend.

---

## Development

```bash
# Install deps (including dev)
uv sync

# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_config.py::test_llm_roundtrip

# Launch the TUI
uv run python main.py
```

---

## Architecture

```
src/trawler/
├── app.py              # TrawlerApp — main Textual application + COMMAND_TREE
├── config.py           # TrawlerConfig — TOML-backed settings
├── index_state.py      # IndexState — tracks which files are embedded
├── rules/              # YARA rule files (.yar / .yara)
├── search/
│   ├── basic.py        # Regex line search
│   ├── ripgrep.py      # python-ripgrep wrapper
│   ├── yara_scan.py    # YARA scanning backend
│   ├── semantic.py     # LangChain + ChromaDB vector search
│   └── local_llm.py    # Local (mlx / llama-cpp) and remote LLM backend
└── widgets/
    ├── command_bar.py  # Input widget with command + path autocomplete
    ├── results_panel.py# RichLog results display with streaming Static overlay
    ├── sidebar.py      # Directory list with indexing stats
    └── status_bar.py   # Single-line status indicator
```

Project-local data lives in `.trawler/` (gitignored):

```
.trawler/
├── config.toml         # Settings (including LLM config)
├── index_state.json    # Per-file mtime + size records
└── chroma/             # ChromaDB vector store
```
