# wsl-files

A small local MCP server that lets an MCP client on Windows (Claude Desktop's Cowork, in particular) read and write files inside WSL. Cowork can't mount `\\wsl.localhost` folders; this server runs inside WSL and does the file work for it.

It runs over stdio, started by the client with `wsl.exe`.

## What it can do

| Tool | What it does |
|---|---|
| `list_roots` | Shows the folders it may use |
| `read_file` | Reads a text file with line numbers, in pages (`offset`, `limit`) |
| `write_file` | Creates or replaces a file, creating parent folders |
| `edit_file` | Replaces exact text: one match, or every match with `replace_all` |
| `list_dir` | Lists a folder, up to 5 levels deep |
| `find_files` | Finds files by glob (`*.md`, `docs/**/*.py`) |
| `search` | Regex search through file contents |

There is no delete and no move, on purpose.

## What it refuses

- **Anything outside the roots.** The default root is `~/dev`. A symlink that points outside is refused too, and paths are checked after resolving symlinks.
- **Secrets files** (`.env`, `token.json`, `*.creds.json`, SSH keys, cookies and similar). It won't read, write, or search them. The patterns are a copy of a Claude Code guard hook's, so both refuse the same files.
- **Key-shaped strings in output** (API keys, tokens, private keys) come back as `[redacted <kind>]`.
- **Writes inside `.git`.**
- **Edits to non-UTF-8 files**, and binary files for any reading.

Every write and edit is logged as one JSON line in `~/.local/state/wsl-files/changes.log`.

## Paths it understands

All of these name the same file:

- `~/dev/proj/README.md`
- `/home/<user>/dev/proj/README.md`
- `proj/README.md` (relative to the first root)
- `\\wsl.localhost\<distro>\home\<user>\dev\proj\README.md` (also `\\wsl$\...`)
- `W:\home\<user>\dev\proj\README.md` (a drive letter mapped to the WSL root; set it with `WSL_FILES_WSL_DRIVE`)
- `C:\Users\<user>\dev\proj\README.md` (a Windows junction to `~/dev`)

## Setup

```bash
cd ~/dev/cowork-wsl-files
uv venv && uv pip install -e ".[dev]"
git config core.hooksPath .githooks
.venv/bin/pytest
```

In `%APPDATA%\Claude\claude_desktop_config.json`, under `mcpServers`:

```json
"wsl-files": {
  "command": "wsl.exe",
  "args": ["-d", "<distro>", "--", "/home/<user>/dev/cowork-wsl-files/scripts/run-server.sh"]
}
```

Restart Claude Desktop afterwards.

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `WSL_FILES_ROOTS` | `~/dev` | Allowed folders, separated by `:`; the first one is where relative paths start |
| `WSL_FILES_WSL_DRIVE` | `W` | Windows drive letter mapped to the WSL root |
| `WSL_FILES_WINDOWS_USER` | `$USER` | User in `C:\Users\<user>\dev` |
| `WSL_FILES_STATE` | `~/.local/state/wsl-files` | Where `changes.log` goes |
