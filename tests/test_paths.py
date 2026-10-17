import os

import pytest

from wsl_files.paths import FilesError, resolve, translate


@pytest.mark.parametrize("given, expected", [
    (r"\\wsl.localhost\Ubuntu-24.04\home\someone\dev\proj\a.md", "/home/someone/dev/proj/a.md"),
    (r"\\wsl$\Ubuntu\home\someone\dev", "/home/someone/dev"),
    ("//wsl.localhost/Ubuntu/home/someone/x", "/home/someone/x"),
    (r"\\wsl.localhost\Ubuntu", "/"),
    (r"W:\home\someone\dev\proj", "/home/someone/dev/proj"),
    (r"w:/home/someone", "/home/someone"),
    ("~/dev/proj", "~/dev/proj"),
    ("proj/a.md", "proj/a.md"),
    ('"/home/someone/dev/a b.md"', "/home/someone/dev/a b.md"),
])
def test_translate(given, expected):
    assert translate(given) == expected


def test_translate_windows_dev_junction(monkeypatch):
    monkeypatch.setenv("WSL_FILES_WINDOWS_USER", "someone")
    home_dev = os.path.expanduser("~/dev")
    assert translate(r"C:\Users\someone\dev\proj\a.md") == home_dev + "/proj/a.md"
    assert translate(r"c:\users\SOMEONE\dev") == home_dev
    # dev.claude is a different folder, not inside the junction
    with pytest.raises(FilesError, match="outside ~/dev"):
        translate(r"C:\Users\someone\dev.claude\NOW.md")
    with pytest.raises(FilesError, match="outside ~/dev"):
        translate(r"D:\Models\x")


def test_relative_and_absolute_resolve_to_same_file(root):
    (root / "proj").mkdir()
    (root / "proj" / "a.md").write_text("x")
    want = str(root / "proj" / "a.md")
    assert resolve("proj/a.md") == want
    assert resolve(want) == want
    assert resolve(str(root) + "/proj/../proj/a.md") == want


def test_dotdot_escape_refused(root):
    with pytest.raises(FilesError, match="outside the folders"):
        resolve("../outside/x.txt")


def test_root_prefix_is_not_a_root(root, tmp_path):
    # /tmp/.../root-evil starts with the root's text but is a different folder
    (tmp_path / "root-evil").mkdir()
    with pytest.raises(FilesError, match="outside"):
        resolve(str(tmp_path / "root-evil" / "x"))


def test_symlink_out_of_root_refused(root, tmp_path):
    (tmp_path / "outside" / "notes.md").write_text("private")
    (root / "link.md").symlink_to(tmp_path / "outside" / "notes.md")
    with pytest.raises(FilesError, match="resolves to"):
        resolve("link.md")


def test_symlink_inside_root_allowed(root):
    (root / "real.md").write_text("x")
    (root / "alias.md").symlink_to(root / "real.md")
    assert resolve("alias.md") == str(root / "real.md")


@pytest.mark.parametrize("name", [".env", ".env.local", "token.json", "my.creds.json", "client_secret_123.json",
                                  "id_ed25519", "server-key.pem", "cookies.json", ".netrc", "credentials.json"])
def test_secret_names_refused(root, name):
    with pytest.raises(FilesError, match="secrets file"):
        resolve(name)


@pytest.mark.parametrize("name", [".env.example", "tokens.md", "environment.py", "key.md"])
def test_ordinary_names_allowed(root, name):
    assert resolve(name) == str(root / name)


def test_secret_behind_innocent_symlink_refused(root):
    (root / ".env").write_text("A=1")
    (root / "notes.txt").symlink_to(root / ".env")
    with pytest.raises(FilesError, match="secrets file"):
        resolve("notes.txt")


def test_git_folder_write_refused_read_allowed(root):
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]")
    assert resolve(".git/config") == str(root / ".git" / "config")
    with pytest.raises(FilesError, match=r"\.git"):
        resolve(".git/config", write=True)


def test_empty_path_refused(root):
    with pytest.raises(FilesError, match="No path"):
        resolve("  ")


def test_multiple_roots(root, tmp_path, monkeypatch):
    second = tmp_path / "second"
    second.mkdir()
    monkeypatch.setenv("WSL_FILES_ROOTS", f"{root}:{second}")
    assert resolve(str(second / "a")) == str(second / "a")
    assert resolve("a") == str(root / "a")  # relative paths start at the first root
