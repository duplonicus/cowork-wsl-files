# wsl-files

Local stdio MCP server so Cowork (Claude Desktop) can read and write files under ~/dev in WSL. State and plans: `NOW.md` (in dev.claude/cowork-wsl-files; the folder names match, so no symlink).

## Rules

- **Every path goes through `paths.resolve`**, and every walked file is checked with `inside_roots`. No tool touches the filesystem with a path that skipped those checks.
- **`secrets.py` is a copy of guard.py rule 6** (`~/.claude/hooks/guard.py`). Change the two together.
- **No delete or move tools.** That's the design; ask dup before adding either.
- **Every tool returns a plain sentence on failure**, never a traceback.
- stdout is the MCP channel in `server.py` and `scripts/run-server.sh`: print nothing there.
- Tests use `tmp_path` roots and made-up content only.

## Layout

- `wsl_files/paths.py`: path translation (Windows spellings), roots, refusals. `ops.py`: the operations. `server.py`: the tools. `secrets.py`: secret names and redaction.
- `tests/`: `.venv/bin/pytest`. `test_stdio.py` starts the real server over stdio.
