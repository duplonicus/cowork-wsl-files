# wsl-files

Local stdio MCP server so Cowork (Claude Desktop) can read and write files under ~/dev in WSL. Public repo.

## Rules

- **Every path goes through `paths.resolve`**, and every walked file is checked with `inside_roots`. No tool touches the filesystem with a path that skipped those checks.
- **`secrets.py` mirrors the maintainer's Claude Code guard hook** (not in this repo), so both refuse the same files. Keep them in step.
- **No delete or move tools.** That's the design; don't add either without the maintainer's OK.
- **Every tool returns a plain sentence on failure**, never a traceback.
- stdout is the MCP channel in `server.py` and `scripts/run-server.sh`: print nothing there.
- Tests use `tmp_path` roots and made-up content only. No real user names, paths or IDs anywhere in the repo.

## Layout

- `wsl_files/paths.py`: path translation (Windows spellings), roots, refusals. `ops.py`: the operations. `server.py`: the tools. `secrets.py`: secret names and redaction.
- `tests/`: `.venv/bin/pytest`. `test_stdio.py` starts the real server over stdio.
