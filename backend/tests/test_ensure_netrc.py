import tempfile

import requests.utils

from app.main import ensure_netrc


def _env(monkeypatch, tmp_path, user="u1", pw="p1"):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("NETRC", raising=False)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    for k, v in (("EARTHDATA_USERNAME", user), ("EARTHDATA_PASSWORD", pw)):
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    return home


def test_writes_netrc_from_env(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    path = ensure_netrc()
    assert path is not None
    assert "machine urs.earthdata.nasa.gov login u1 password p1" in open(path).read()
    import os

    assert os.environ["NETRC"] == path
    assert requests.utils.get_netrc_auth("https://urs.earthdata.nasa.gov/") == ("u1", "p1")


def test_existing_home_netrc_kept(monkeypatch, tmp_path):
    home = _env(monkeypatch, tmp_path)
    (home / ".netrc").write_text("machine x login a password b\n")
    assert ensure_netrc() is None
    assert not (tmp_path / "luzsi.netrc").exists()


def test_existing_netrc_env_kept(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    monkeypatch.setenv("NETRC", "/some/netrc")
    assert ensure_netrc() is None


def test_missing_creds_no_write(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, pw=None)
    assert ensure_netrc() is None
    assert not (tmp_path / "luzsi.netrc").exists()
