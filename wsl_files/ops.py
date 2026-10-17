"""The file operations behind each tool. Every path goes through paths.resolve first."""

import fnmatch
import json
import os
import re
import tempfile
import time

from .paths import SKIP_DIRS, FilesError, display, inside_roots, resolve
from .secrets import redact, secret_path

MAX_READ_BYTES = 2_000_000
MAX_READ_CHARS = 200_000
MAX_SEARCH_FILE_BYTES = 1_000_000
MAX_LINE_CHARS = 2000


def _is_binary(chunk: bytes) -> bool:
    return b"\0" in chunk


def _read_text(real: str, path: str) -> str:
    if os.path.isdir(real):
        raise FilesError(f"{path} is a folder. Use list_dir for folders.")
    if not os.path.exists(real):
        raise FilesError(f"{path} does not exist.")
    size = os.path.getsize(real)
    if size > MAX_READ_BYTES:
        raise FilesError(f"{path} is {size:,} bytes, over the {MAX_READ_BYTES:,}-byte limit for reading.")
    with open(real, "rb") as f:
        data = f.read()
    if _is_binary(data[:8192]):
        raise FilesError(f"{path} is a binary file; only text files can be read.")
    return data.decode("utf-8", errors="replace")


def log_change(tool: str, real: str, detail: dict) -> None:
    """One JSON line per write or edit, so every change Cowork made can be found later."""
    state = os.environ.get("WSL_FILES_STATE") or os.path.expanduser("~/.local/state/wsl-files")
    try:
        os.makedirs(state, exist_ok=True)
        with open(os.path.join(state, "changes.log"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tool": tool, "path": real, **detail}) + "\n")
    except OSError:
        pass  # the log is an audit aid; a full disk must not fail the write itself


def read_file(path: str, offset: int = 1, limit: int = 2000) -> str:
    real = resolve(path)
    text = _read_text(real, path)
    lines = text.splitlines()
    if not lines:
        return f"{display(real)} is empty."
    start = max(offset, 1)
    if start > len(lines):
        raise FilesError(f"{display(real)} has {len(lines)} lines; offset {offset} is past the end.")
    end = min(start - 1 + max(limit, 1), len(lines))
    out, used = [], 0
    for n in range(start, end + 1):
        line = lines[n - 1]
        if len(line) > MAX_LINE_CHARS:
            line = line[:MAX_LINE_CHARS] + " [line cut]"
        row = f"{n:>6}\t{line}"
        if used + len(row) > MAX_READ_CHARS:
            end = n - 1
            break
        out.append(row)
        used += len(row) + 1
    head = f"{display(real)} (lines {start}-{end} of {len(lines)})"
    if end < len(lines):
        head += f"; read on with offset={end + 1}"
    return head + "\n" + redact("\n".join(out))


def _atomic_write(real: str, data: str) -> None:
    folder = os.path.dirname(real)
    mode = os.stat(real).st_mode & 0o7777 if os.path.exists(real) else None
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".wsl-files-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(data)
        if mode is not None:
            os.chmod(tmp, mode)
        else:
            os.chmod(tmp, 0o666 & ~_umask())
        os.replace(tmp, real)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _is_utf8(real: str) -> bool:
    try:
        with open(real, "rb") as f:
            f.read().decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


def write_file(path: str, content: str) -> str:
    # resolve() returns the real file, so writing to a symlink updates its target
    # instead of replacing the link with a plain file.
    real = resolve(path, write=True)
    if os.path.isdir(real):
        raise FilesError(f"{path} is a folder, not a file.")
    existed = os.path.exists(real)
    os.makedirs(os.path.dirname(real), exist_ok=True)
    _atomic_write(real, content)
    size = len(content.encode("utf-8"))
    log_change("write_file", real, {"bytes": size, "replaced": existed})
    return f"{'Replaced' if existed else 'Created'} {display(real)} ({size:,} bytes)."


def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    real = resolve(path, write=True)
    text = _read_text(real, path)
    if "\ufffd" in text and not _is_utf8(real):
        raise FilesError(f"{display(real)} is not UTF-8 text; editing it here could damage it.")
    if old_string == new_string:
        raise FilesError("old_string and new_string are the same; nothing to change.")
    if not old_string:
        raise FilesError("old_string is empty. To write a whole file, use write_file.")
    old, new = old_string, new_string
    # A CRLF file edited with LF text from the client: match on the file's own line endings.
    if old not in text and "\r\n" in text and "\r\n" not in old:
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    count = text.count(old)
    if count == 0:
        raise FilesError(f"old_string was not found in {display(real)}. Read the file and copy the text exactly, "
                         "without the line-number prefix.")
    if count > 1 and not replace_all:
        raise FilesError(f"old_string appears {count} times in {display(real)}. Add surrounding text so it is unique, "
                         "or set replace_all.")
    _atomic_write(real, text.replace(old, new) if replace_all else text.replace(old, new, 1))
    done = count if replace_all else 1
    log_change("edit_file", real, {"replacements": done})
    return f"Edited {display(real)}: {done} replacement{'s' if done != 1 else ''}."


def list_dir(path: str = "", depth: int = 1) -> str:
    real = resolve(path or ".")
    if not os.path.isdir(real):
        raise FilesError(f"{path} is not a folder." if os.path.exists(real) else f"{path} does not exist.")
    depth = min(max(depth, 1), 5)
    rows: list[str] = []
    limit = 1000

    def walk(folder: str, level: int) -> None:
        try:
            entries = sorted(os.scandir(folder), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            rows.append("  " * level + "(no permission)")
            return
        for e in entries:
            if len(rows) >= limit:
                return
            indent = "  " * level
            if e.is_symlink() and not inside_roots(os.path.realpath(e.path)):
                rows.append(f"{indent}{e.name} -> outside the allowed folders")
            elif e.is_dir(follow_symlinks=True):
                skipped = e.name in SKIP_DIRS or e.is_symlink()
                rows.append(f"{indent}{e.name}/" + ("  (skipped)" if skipped and level + 1 < depth else ""))
                if level + 1 < depth and not skipped:
                    walk(e.path, level + 1)
            else:
                try:
                    size = e.stat().st_size
                except OSError:
                    size = 0
                rows.append(f"{indent}{e.name}  {size:,} B")

    walk(real, 0)
    more = "\n(listing cut at 1,000 entries; list a subfolder)" if len(rows) >= limit else ""
    return f"{display(real)}/\n" + ("\n".join(rows) if rows else "(empty)") + more


def _walk_files(real: str):
    """Files under a folder, skipping SKIP_DIRS. os.walk does not enter symlinked folders;
    a symlinked file is only yielded when it points inside the roots."""
    for folder, dirs, files in os.walk(real):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            f = os.path.join(folder, name)
            if not os.path.islink(f) or inside_roots(os.path.realpath(f)):
                yield f


def _glob_match(rel: str, pattern: str) -> bool:
    if fnmatch.fnmatch(rel, pattern):
        return True
    if pattern.startswith("**/") and fnmatch.fnmatch(rel, pattern[3:]):
        return True
    return "/" not in pattern and fnmatch.fnmatch(os.path.basename(rel), pattern)


def find_files(pattern: str, path: str = "", max_results: int = 200) -> str:
    real = resolve(path or ".")
    if not os.path.isdir(real):
        raise FilesError(f"{path} is not a folder.")
    hits = []
    for f in _walk_files(real):
        rel = os.path.relpath(f, real)
        if _glob_match(rel, pattern):
            hits.append(rel)
            if len(hits) >= max_results:
                break
    if not hits:
        return f"No files matching {pattern} under {display(real)}."
    cut = f"\n(stopped at {max_results} results)" if len(hits) >= max_results else ""
    return f"{len(hits)} file(s) under {display(real)}:\n" + "\n".join(hits) + cut


def search(pattern: str, path: str = "", glob: str = "", ignore_case: bool = False, max_results: int = 100) -> str:
    real = resolve(path or ".")
    try:
        rx = re.compile(pattern, re.I if ignore_case else 0)
    except re.error as exc:
        raise FilesError(f"Bad regular expression: {exc}") from exc
    files = [real] if os.path.isfile(real) else _walk_files(real)
    base = os.path.dirname(real) if os.path.isfile(real) else real
    hits = []
    for f in files:
        rel = os.path.relpath(f, base)
        if glob and not _glob_match(rel, glob):
            continue
        if secret_path(f):
            continue
        try:
            if os.path.getsize(f) > MAX_SEARCH_FILE_BYTES:
                continue
            with open(f, "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        if _is_binary(data[:8192]):
            continue
        for n, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel}:{n}: {redact(line.strip()[:300])}")
                if len(hits) >= max_results:
                    break
        if len(hits) >= max_results:
            break
    if not hits:
        return f"No matches for {pattern} under {display(real)}."
    cut = f"\n(stopped at {max_results} matches; narrow the path or glob)" if len(hits) >= max_results else ""
    return f"{len(hits)} match(es) under {display(base)}:\n" + "\n".join(hits) + cut
