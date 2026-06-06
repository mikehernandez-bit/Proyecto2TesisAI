import json
import os
import time

from app.core.storage.json_store import JsonStore


def test_write_list_replaces_existing_file_atomically(tmp_path):
    path = tmp_path / "projects.json"
    store = JsonStore(str(path))

    store.write_list([{"id": "old"}])
    store.write_list([{"id": "new", "value": 1}])

    assert json.loads(path.read_text(encoding="utf-8")) == [{"id": "new", "value": 1}]
    assert not list(tmp_path.glob("*.tmp"))


def test_write_list_removes_stale_temp_files(tmp_path):
    path = tmp_path / "projects.json"
    stale = tmp_path / ".projects.json.deadbeef.tmp"
    stale.write_text("", encoding="utf-8")
    old_time = time.time() - 120
    os.utime(stale, (old_time, old_time))
    store = JsonStore(str(path))

    store.write_list([{"id": "clean"}])

    assert json.loads(path.read_text(encoding="utf-8")) == [{"id": "clean"}]
    assert not stale.exists()
    assert not list(tmp_path.glob(".projects.json.*.tmp"))


def test_write_list_cleans_temp_file_when_temp_write_fails(tmp_path, monkeypatch):
    path = tmp_path / "projects.json"
    store = JsonStore(str(path))
    original_write_text = type(path).write_text

    def blocked_temp_write(self, text, *args, **kwargs):
        if self.name.startswith(".projects.json.") and self.suffix == ".tmp":
            original_write_text(self, "", *args, **kwargs)
            raise OSError("temporary write failed")
        return original_write_text(self, text, *args, **kwargs)

    monkeypatch.setattr(type(path), "write_text", blocked_temp_write)

    try:
        store.write_list([{"id": "new"}])
    except OSError as exc:
        assert "temporary write failed" in str(exc)
    else:
        raise AssertionError("Expected temp write failure")

    assert not list(tmp_path.glob(".projects.json.*.tmp"))


def test_write_list_falls_back_when_atomic_replace_is_blocked(tmp_path, monkeypatch):
    path = tmp_path / "projects.json"
    store = JsonStore(str(path))
    store.write_list([{"id": "old"}])

    def blocked_replace(src, dst):
        raise PermissionError("destination is temporarily locked")

    monkeypatch.setattr("app.core.storage.json_store.os.replace", blocked_replace)

    store.write_list([{"id": "new", "value": 1}])

    assert json.loads(path.read_text(encoding="utf-8")) == [{"id": "new", "value": 1}]
    assert not list(tmp_path.glob("*.tmp"))
