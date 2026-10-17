"""Starts the real server through scripts/run-server.sh and talks MCP to it over stdio."""

import os
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run-server.sh"


async def _session(root, state, calls):
    env = {**os.environ, "WSL_FILES_ROOTS": str(root), "WSL_FILES_STATE": str(state)}
    params = StdioServerParameters(command=str(SCRIPT), env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            results = []
            for name, args in calls:
                r = await session.call_tool(name, args)
                results.append((r.isError, r.content[0].text))
            return init, tools, results


def test_stdio_roundtrip(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    init, tools, results = anyio.run(_session, root, tmp_path / "state", [
        ("write_file", {"path": "notes/a.md", "content": "hello\nworld\n"}),
        ("edit_file", {"path": "notes/a.md", "old_string": "world", "new_string": "there"}),
        ("read_file", {"path": str(root / "notes" / "a.md")}),
        ("read_file", {"path": "/etc/passwd"}),
        ("list_roots", {}),
    ])
    assert init.serverInfo.name == "wsl-files"
    assert init.instructions and "WSL" in init.instructions
    assert {t.name for t in tools.tools} == {
        "list_roots", "read_file", "write_file", "edit_file", "list_dir", "find_files", "search",
        "copy_to_windows", "copy_from_windows"}
    read_only = {t.name for t in tools.tools if t.annotations.readOnlyHint}
    assert read_only == {"list_roots", "read_file", "list_dir", "find_files", "search"}
    (_, wrote), (_, edited), (_, read), (_, refused), (_, roots) = results
    assert wrote.startswith("Created")
    assert edited.startswith("Edited")
    assert read.splitlines()[1:] == ["     1\thello", "     2\tthere"]
    assert "outside the folders" in refused
    assert roots == str(root)
    assert (root / "notes" / "a.md").read_text() == "hello\nthere\n"
