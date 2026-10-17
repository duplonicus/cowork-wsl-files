"""Turn whatever path the client sends into a real path inside an allowed root, or refuse.

Clients on the Windows side send Windows spellings of WSL paths, so these are accepted:
  ~/dev/x, /home/<user>/dev/x, a path relative to the first root,
  \\\\wsl.localhost\\<distro>\\home\\..., \\\\wsl$\\<distro>\\home\\...,
  W:\\home\\... (W: is mapped to the WSL root on this machine, see WSL_FILES_WSL_DRIVE),
  C:\\Users\\<user>\\dev\\... (a Windows junction to ~/dev).
"""

import os
import re

from .secrets import secret_path


class FilesError(Exception):
    """A refusal or failure, worded for the person reading the tool result."""


SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}

_UNC = re.compile(r"^(?:\\\\|//)(?:wsl\.localhost|wsl\$)[\\/][^\\/]+(?P<rest>(?:[\\/].*)?)$", re.I)
_DRIVE = re.compile(r"^(?P<drive>[A-Za-z]):(?P<rest>(?:[\\/].*)?)$")


def roots() -> list[str]:
    """Allowed roots, real paths. WSL_FILES_ROOTS is a colon-separated list; default ~/dev."""
    raw = os.environ.get("WSL_FILES_ROOTS") or "~/dev"
    out = []
    for r in raw.split(os.pathsep):
        if r.strip():
            out.append(os.path.realpath(os.path.expanduser(r.strip())))
    return out


def staging() -> str | None:
    """The one Windows folder copy_to_windows / copy_from_windows may use (WSL path), or None when unset.
    WSL_FILES_STAGING may be a Windows spelling (C:\\Users\\<user>\\Claude\\wsl-staging)."""
    raw = os.environ.get("WSL_FILES_STAGING")
    if not raw:
        return None
    m = _DRIVE.match(raw.strip())
    p = f"/mnt/{m['drive'].lower()}{(m['rest'] or '/').replace(chr(92), '/')}" if m else raw
    return os.path.realpath(os.path.expanduser(p))


def resolve_staging(name: str) -> str:
    """A file inside the staging folder, by name or relative path. Refuses anything that leaves it."""
    st = staging()
    if not st:
        raise FilesError("No staging folder is set (WSL_FILES_STAGING), so copying to or from Windows is off.")
    n = name.strip().strip('"').replace("\\", "/")
    if m := _DRIVE.match(n):  # a full Windows path into the staging folder is fine too
        n = f"/mnt/{m['drive'].lower()}{(m['rest'] or '/')}"
    real = os.path.realpath(n if os.path.isabs(n) else os.path.join(st, n))
    if not _inside(real, st) or real == st:
        raise FilesError(f"{name} is not a file inside the staging folder {st}.")
    if secret_path(real):
        raise FilesError(f"{name} looks like a secrets file. This server never reads or writes those.")
    return real


def _wsl_drive() -> str:
    return (os.environ.get("WSL_FILES_WSL_DRIVE") or "W").upper()


def _windows_dev() -> str:
    """The Windows spelling of ~/dev's junction: C:\\Users\\<user>\\dev."""
    user = os.environ.get("WSL_FILES_WINDOWS_USER") or os.environ.get("USER") or ""
    return f"c:/users/{user}/dev".lower()


def translate(path: str) -> str:
    """Rewrite a Windows spelling to the WSL path it names. Other input is returned as is."""
    p = path.strip().strip('"')
    if m := _UNC.match(p):
        return (m["rest"] or "/").replace("\\", "/")
    if m := _DRIVE.match(p):
        rest = (m["rest"] or "/").replace("\\", "/")
        if m["drive"].upper() == _wsl_drive():
            return rest
        win = f"{m['drive']}:{rest}".lower()
        junction = _windows_dev()
        if win == junction or win.startswith(junction + "/"):
            return os.path.expanduser("~/dev") + rest[len(junction) - 2:]
        raise FilesError(
            f"{path} is a Windows path outside ~/dev. This server only reaches files inside WSL; "
            "use your own file access for Windows folders.")
    return p


def _inside(real: str, root: str) -> bool:
    return real == root or real.startswith(root.rstrip("/") + "/")


def inside_roots(real: str) -> bool:
    return any(_inside(real, r) for r in roots())


def resolve(path: str, *, write: bool = False) -> str:
    """The real path for `path`, after every check. Raises FilesError with the reason."""
    if not path or not path.strip():
        raise FilesError("No path given.")
    allowed = roots()
    p = os.path.expanduser(translate(path))
    if not os.path.isabs(p):
        p = os.path.join(allowed[0], p)
    p = os.path.normpath(p)
    # Checked on the name asked for and on the file it really is, so a symlink can't hide a secret.
    real = os.path.realpath(p)
    if not any(_inside(real, r) for r in allowed):
        where = p if real == p else f"{p} (it resolves to {real})"
        raise FilesError(f"{where} is outside the folders this server may use: {', '.join(allowed)}.")
    if secret_path(p) or secret_path(real):
        raise FilesError(f"{p} looks like a secrets file. This server never reads or writes those.")
    if write and ".git" in real.split("/"):
        raise FilesError(f"{p} is inside a .git folder. Git's own files are not edited through this server.")
    return real


def display(real: str) -> str:
    """A path as the client should see it: ~/... when under home."""
    home = os.path.expanduser("~")
    return "~" + real[len(home):] if _inside(real, home) else real
