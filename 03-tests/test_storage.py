import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import numpy as np
import storage


def test_get_video_path_returns_string():
    assert isinstance(storage.get_video_path(), str)


def test_get_video_path_ends_with_mp4():
    assert storage.get_video_path().endswith(".mp4")


def test_get_video_path_contains_motion_prefix():
    assert "motion_" in storage.get_video_path()


def test_get_snapshot_path_returns_string():
    assert isinstance(storage.get_snapshot_path(), str)


def test_get_snapshot_path_ends_with_jpg():
    assert storage.get_snapshot_path().endswith(".jpg")


def test_get_snapshot_path_contains_snapshot_prefix():
    assert "snapshot_" in storage.get_snapshot_path()


def test_save_snapshot_returns_path(tmp_path, monkeypatch):
    # Redirect CLIPS_DIR to a temporary directory so no real files are created
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    monkeypatch.setattr(storage, "get_snapshot_path", lambda: str(tmp_path / "snapshot_test.jpg"))

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    result = storage.save_snapshot(frame)
    assert result == str(tmp_path / "snapshot_test.jpg")


def test_save_snapshot_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    monkeypatch.setattr(storage, "get_snapshot_path", lambda: str(tmp_path / "snapshot_test.jpg"))

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    path = storage.save_snapshot(frame)
    assert os.path.exists(path)


def test_cleanup_removes_old_mp4(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    old_file = tmp_path / "motion_old.mp4"
    old_file.write_text("x")
    old_time = __import__("time").time() - (8 * 86400)
    __import__("os").utime(str(old_file), (old_time, old_time))
    storage.cleanup_old_clips(days=7)
    assert not old_file.exists()


def test_cleanup_keeps_recent_mp4(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    recent = tmp_path / "motion_recent.mp4"
    recent.write_text("x")
    storage.cleanup_old_clips(days=7)
    assert recent.exists()


def test_cleanup_removes_old_h264(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    orphan = tmp_path / "motion_old.h264"
    orphan.write_text("x")
    old_time = __import__("time").time() - 400
    __import__("os").utime(str(orphan), (old_time, old_time))
    storage.cleanup_old_clips(days=7)
    assert not orphan.exists()


def test_cleanup_keeps_active_h264(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    active = tmp_path / "motion_active.h264"
    active.write_text("x")
    storage.cleanup_old_clips(days=7)
    assert active.exists()


def test_cleanup_skips_subdirectories(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    subdir = tmp_path / "archive"
    subdir.mkdir()
    old_file = subdir / "motion_old.mp4"
    old_file.write_text("x")
    old_time = __import__("time").time() - (8 * 86400)
    __import__("os").utime(str(old_file), (old_time, old_time))
    storage.cleanup_old_clips(days=7)
    assert old_file.exists()


def test_cleanup_does_not_raise_if_file_deleted_concurrently(tmp_path, monkeypatch):
    """cleanup_old_clips() must not raise if another thread removes a file mid-scan."""
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    old_file = tmp_path / "motion_old.mp4"
    old_file.write_text("x")
    old_time = __import__("time").time() - (8 * 86400)
    __import__("os").utime(str(old_file), (old_time, old_time))

    original_remove = os.remove

    def remove_then_raise(path):
        original_remove(path)
        raise FileNotFoundError(f"already gone: {path}")

    monkeypatch.setattr(storage.os, "remove", remove_then_raise)
    storage.cleanup_old_clips(days=7)  # must not raise


def test_save_snapshot_raises_if_imwrite_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    monkeypatch.setattr(storage, "get_snapshot_path", lambda: str(tmp_path / "snap.jpg"))
    monkeypatch.setattr(storage.cv2, "imwrite", lambda *a, **kw: False)

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    with pytest.raises(RuntimeError, match="cv2.imwrite failed"):
        storage.save_snapshot(frame)
