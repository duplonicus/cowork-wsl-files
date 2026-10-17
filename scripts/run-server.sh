#!/usr/bin/env bash
# Entry point for MCP clients (Claude Desktop/Cowork via wsl.exe, Claude Code).
# stdout is the MCP channel: nothing here may print to it.
# Settings (WSL_FILES_*) come from config.local next to this repo's README, if present: env vars set
# in the Desktop config stay on the Windows side and never reach WSL.
here="$(dirname "${BASH_SOURCE[0]}")/.."
if [ -f "$here/config.local" ]; then set -a; . "$here/config.local"; set +a; fi
exec "$here/.venv/bin/python" -m wsl_files.server
