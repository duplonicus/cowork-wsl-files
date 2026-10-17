# wsl-files

A small local MCP server that lets Claude Desktop's Cowork, on Windows, read and write your files inside WSL.

It runs inside WSL over stdio, and Claude Desktop starts it with `wsl.exe`.

## Why this exists

Cowork on Windows can't attach a folder that lives in a WSL distro. Every way in fails:

- A `\\wsl.localhost\<distro>\...` subfolder is rejected up front: "Network (UNC) paths are not supported here."
- The `\\wsl.localhost` folder itself, a mapped drive (`net use`), a `subst` drive, or a symlink in your Windows home folder: the picker accepts them, then the message fails with "Some folders couldn't be added."

That leaves WSL developers without Cowork for any of their code. Microsoft's own advice is to keep projects on the Linux filesystem for speed ([WSL docs](https://learn.microsoft.com/en-us/windows/wsl/filesystems)).

The feature request is [anthropics/claude-code#99303](https://github.com/anthropics/claude-code/issues/99303). It re-files [#61003](https://github.com/anthropics/claude-code/issues/61003), which a bot closed as stale with no maintainer response. Claude Desktop's Code tab does handle WSL folders; Cowork doesn't.

Cowork can still use local MCP servers through Claude Desktop, and an MCP server can run inside WSL. This one does the file work there and hands Cowork the results.

### Why not the official filesystem server

[`@modelcontextprotocol/server-filesystem`](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) works, but two things made it a poor fit here:

- **No server-side deny list.** Anything under an allowed folder is readable, `.env` files included; its `excludePatterns` is a per-call option for searches, chosen by the client. This server refuses secrets files outright and redacts key-shaped strings.
- **The client can replace its folders.** Per its README, roots sent by the client "completely replace any server-side Allowed directories". Here the folders are fixed on the server side, whatever the client sends.

This one also accepts the Windows spellings Cowork tends to send (`\\wsl.localhost\...`, `W:\...`, `C:\Users\<user>\dev\...`).

If Anthropic ships WSL folders in Cowork, you won't need this.

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
