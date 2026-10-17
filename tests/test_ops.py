import json
import os
import stat

import pytest

from wsl_files import ops
from wsl_files.paths import FilesError

FAKE_GH = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0"


def changes(tmp_path):
    log = tmp_path / "state" / "changes.log"
    return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []


# ---------------------------------------------------------------- read

def test_read_numbers_lines_and_pages(root):
    (root / "a.md").write_text("one\ntwo\nthree\nfour\n")
    out = ops.read_file("a.md", offset=2, limit=2)
    head, *rows = out.splitlines()
    assert "lines 2-3 of 4" in head and "offset=4" in head
    assert rows == ["     2\ttwo", "     3\tthree"]


def test_read_whole_file_has_no_continue_hint(root):
    (root / "a.md").write_text("one\ntwo\n")
    out = ops.read_file("a.md")
    assert "lines 1-2 of 2" in out and "offset=" not in out


def test_read_redacts_keys(root):
    (root / "a.py").write_text(f"TOKEN = '{FAKE_GH}'\n")
    out = ops.read_file("a.py")
    assert FAKE_GH not in out and "[redacted GitHub token]" in out


def test_read_refuses_binary_folder_missing_and_past_end(root):
    (root / "b.bin").write_bytes(b"\x00\x01\x02")
    (root / "d").mkdir()
    (root / "a.md").write_text("x\n")
    with pytest.raises(FilesError, match="binary"):
        ops.read_file("b.bin")
    with pytest.raises(FilesError, match="folder"):
        ops.read_file("d")
    with pytest.raises(FilesError, match="does not exist"):
        ops.read_file("nope.md")
    with pytest.raises(FilesError, match="past the end"):
        ops.read_file("a.md", offset=5)


def test_read_empty_file(root):
    (root / "e.md").write_text("")
    assert "is empty" in ops.read_file("e.md")


# ---------------------------------------------------------------- write

def test_write_creates_with_parents_then_replaces(root, tmp_path):
    msg = ops.write_file("new/deep/a.md", "héllo\n")
    assert msg.startswith("Created") and "7 bytes" in msg
    assert (root / "new" / "deep" / "a.md").read_text() == "héllo\n"
    msg = ops.write_file("new/deep/a.md", "bye")
    assert msg.startswith("Replaced")
    assert (root / "new" / "deep" / "a.md").read_text() == "bye"
    log = changes(tmp_path)
    assert [(c["tool"], c["replaced"]) for c in log] == [("write_file", False), ("write_file", True)]
    assert all(c["path"] == str(root / "new" / "deep" / "a.md") for c in log)


def test_write_keeps_crlf_and_mode(root):
    f = root / "run.sh"
    f.write_text("old")
    f.chmod(0o755)
    ops.write_file("run.sh", "a\r\nb\r\n")
    assert f.read_bytes() == b"a\r\nb\r\n"
    assert stat.S_IMODE(f.stat().st_mode) == 0o755


def test_write_through_symlink_updates_target_and_keeps_link(root):
    (root / "real.md").write_text("old")
    (root / "NOW.md").symlink_to(root / "real.md")
    ops.write_file("NOW.md", "new")
    assert (root / "NOW.md").is_symlink()
    assert (root / "real.md").read_text() == "new"


def test_write_leaves_no_temp_files(root):
    ops.write_file("a.md", "x")
    assert sorted(os.listdir(root)) == ["a.md"]


def test_write_refuses_secret_outside_git_and_folder(root, tmp_path):
    (root / "d").mkdir()
    (root / ".git").mkdir()
    for path, why in [(".env", "secrets"), ("../outside/x", "outside"), (".git/HEAD", r"\.git"), ("d", "folder")]:
        with pytest.raises(FilesError, match=why):
            ops.write_file(path, "x")
    assert not (tmp_path / "outside" / "x").exists()
    assert changes(tmp_path) == []


# ---------------------------------------------------------------- edit

def test_edit_single_match(root, tmp_path):
    (root / "a.md").write_text("alpha beta gamma\n")
    assert "1 replacement" in ops.edit_file("a.md", "beta", "BETA")
    assert (root / "a.md").read_text() == "alpha BETA gamma\n"
    assert changes(tmp_path)[-1] == {**changes(tmp_path)[-1], "tool": "edit_file", "replacements": 1}


def test_edit_ambiguous_refused_unless_replace_all(root):
    (root / "a.md").write_text("x x x")
    with pytest.raises(FilesError, match="3 times"):
        ops.edit_file("a.md", "x", "y")
    assert (root / "a.md").read_text() == "x x x"
    assert "3 replacements" in ops.edit_file("a.md", "x", "y", replace_all=True)
    assert (root / "a.md").read_text() == "y y y"


def test_edit_not_found_same_and_empty(root):
    (root / "a.md").write_text("abc")
    with pytest.raises(FilesError, match="not found"):
        ops.edit_file("a.md", "zzz", "y")
    with pytest.raises(FilesError, match="same"):
        ops.edit_file("a.md", "abc", "abc")
    with pytest.raises(FilesError, match="empty"):
        ops.edit_file("a.md", "", "y")


def test_edit_crlf_file_with_lf_text(root):
    (root / "w.md").write_bytes(b"line one\r\nline two\r\nline three\r\n")
    ops.edit_file("w.md", "line one\nline two", "first\nsecond")
    assert (root / "w.md").read_bytes() == b"first\r\nsecond\r\nline three\r\n"


def test_edit_refuses_non_utf8(root):
    data = "caf\xe9 au lait".encode("latin-1")
    (root / "l.txt").write_bytes(data)
    with pytest.raises(FilesError, match="not UTF-8"):
        ops.edit_file("l.txt", "au", "with")
    assert (root / "l.txt").read_bytes() == data


# ---------------------------------------------------------------- list / find / search

def make_tree(root, tmp_path):
    (root / "proj" / "docs").mkdir(parents=True)
    (root / "proj" / "node_modules" / "pkg").mkdir(parents=True)
    (root / "proj" / "README.md").write_text("# Proj\nneedle here\n")
    (root / "proj" / "docs" / "guide.md").write_text("no match\nNEEDLE upper\n")
    (root / "proj" / "app.py").write_text(f"needle = '{FAKE_GH}'\n")
    (root / "proj" / "node_modules" / "pkg" / "x.md").write_text("needle in deps\n")
    (root / "proj" / ".env").write_text("needle=1\n")
    (tmp_path / "outside" / "secret.md").write_text("needle outside\n")
    (root / "proj" / "escape.md").symlink_to(tmp_path / "outside" / "secret.md")
    (tmp_path / "outside" / "dir").mkdir()
    (root / "proj" / "escdir").symlink_to(tmp_path / "outside" / "dir")


def test_list_dir(root, tmp_path):
    make_tree(root, tmp_path)
    out = ops.list_dir("proj", depth=2)
    lines = out.splitlines()
    assert lines[0].endswith("/proj/")
    assert "  guide.md  " in out  # entered docs/
    assert "node_modules/  (skipped)" in out and "pkg" not in out
    assert "escape.md -> outside the allowed folders" in out
    assert "escdir -> outside the allowed folders" in out
    # folders before files
    assert lines.index("docs/") < lines.index(next(l for l in lines if l.startswith("README.md")))


def test_list_dir_default_is_root_and_refuses_files(root):
    (root / "a.md").write_text("x")
    assert "a.md  1 B" in ops.list_dir()
    with pytest.raises(FilesError, match="not a folder"):
        ops.list_dir("a.md")


def test_find_files(root, tmp_path):
    make_tree(root, tmp_path)
    out = ops.find_files("*.md", "proj")
    found = set(out.splitlines()[1:])
    assert found == {"README.md", "docs/guide.md"}  # no node_modules, no link leaving the root
    assert ops.find_files("**/*.md", "proj").splitlines()[1:] == out.splitlines()[1:]
    assert ops.find_files("docs/*.md", "proj").splitlines()[1:] == ["docs/guide.md"]
    assert "No files" in ops.find_files("*.rs", "proj")


def test_search(root, tmp_path):
    make_tree(root, tmp_path)
    out = ops.search("needle", "proj")
    hits = out.splitlines()[1:]
    assert hits == ["README.md:2: needle here", "app.py:1: needle = '[redacted GitHub token]'"]
    # skipped: node_modules, .env, the symlink out of the root; case-sensitive by default


def test_search_options(root, tmp_path):
    make_tree(root, tmp_path)
    assert ops.search("needle", "proj", glob="docs/*", ignore_case=True).splitlines()[1:] == [
        "docs/guide.md:2: NEEDLE upper"]
    assert ops.search("needle", "proj/README.md").splitlines()[1:] == ["README.md:2: needle here"]
    assert "stopped at 1" in ops.search("needle", "proj", max_results=1)
    with pytest.raises(FilesError, match="Bad regular"):
        ops.search("(", "proj")
    assert "No matches" in ops.search("absent", "proj")
