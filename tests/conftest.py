import pytest


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A fresh allowed root, with an outside folder next to it and the change log kept in tmp."""
    r = tmp_path / "root"
    r.mkdir()
    (tmp_path / "outside").mkdir()
    monkeypatch.setenv("WSL_FILES_ROOTS", str(r))
    monkeypatch.setenv("WSL_FILES_STATE", str(tmp_path / "state"))
    return r
