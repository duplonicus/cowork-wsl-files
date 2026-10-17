import pytest

from wsl_files import ops
from wsl_files.paths import FilesError


@pytest.fixture
def staging(root, tmp_path, monkeypatch):
    st = tmp_path / "staging"
    st.mkdir()
    monkeypatch.setenv("WSL_FILES_STAGING", str(st))
    return st


DOCX = b"PK\x03\x04\x00\x00binary\x00body"


def test_copy_to_windows_keeps_bytes_and_name(root, staging):
    (root / "proj").mkdir()
    (root / "proj" / "cv.docx").write_bytes(DOCX)
    assert "Copied to" in ops.copy_to_windows("proj/cv.docx")
    assert (staging / "cv.docx").read_bytes() == DOCX
    assert "Copied to" in ops.copy_to_windows("proj/cv.docx", "sub/renamed.docx")
    assert (staging / "sub" / "renamed.docx").read_bytes() == DOCX
    assert "Replaced" in ops.copy_to_windows("proj/cv.docx")


def test_copy_from_windows_into_root(root, staging):
    (staging / "out.pdf").write_bytes(DOCX)
    ops.copy_from_windows("out.pdf", "proj/state/out.pdf")
    assert (root / "proj" / "state" / "out.pdf").read_bytes() == DOCX
    # a full path into the staging folder works too
    ops.copy_from_windows(str(staging / "out.pdf"), "proj/again.pdf")
    assert (root / "proj" / "again.pdf").read_bytes() == DOCX


def test_staging_escapes_and_secrets_refused(root, staging, tmp_path):
    (tmp_path / "outside" / "x.pdf").write_bytes(DOCX)
    (root / ".env").write_text("A=1")
    (staging / ".env").write_text("A=1")
    for call, why in [
        (lambda: ops.copy_from_windows("../outside/x.pdf", "x.pdf"), "not a file inside the staging"),
        (lambda: ops.copy_from_windows(str(tmp_path / "outside" / "x.pdf"), "x.pdf"), "not a file inside the staging"),
        (lambda: ops.copy_to_windows(".env"), "secrets"),
        (lambda: ops.copy_from_windows(".env", "y.txt"), "secrets"),
        (lambda: ops.copy_from_windows("x.pdf", "../outside/y.pdf"), "outside"),
        (lambda: ops.copy_to_windows("nope.pdf"), "not a file"),
    ]:
        with pytest.raises(FilesError, match=why):
            call()
    assert not (root / "x.pdf").exists()


def test_copy_off_without_staging(root, monkeypatch):
    monkeypatch.delenv("WSL_FILES_STAGING", raising=False)
    (root / "a.pdf").write_bytes(DOCX)
    with pytest.raises(FilesError, match="No staging folder"):
        ops.copy_to_windows("a.pdf")


def test_windows_spelling_of_staging(root, tmp_path, monkeypatch):
    from wsl_files.paths import staging
    monkeypatch.setenv("WSL_FILES_STAGING", r"C:\Users\someone\Claude\wsl-staging")
    assert staging() == "/mnt/c/Users/someone/Claude/wsl-staging"
