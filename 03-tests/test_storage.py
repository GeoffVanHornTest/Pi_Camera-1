import os
import sys

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
    monkeypatch.setattr(
        storage, "get_snapshot_path", lambda: str(tmp_path / "snapshot_test.jpg")
    )

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    result = storage.save_snapshot(frame)
    assert result == str(tmp_path / "snapshot_test.jpg")


def test_save_snapshot_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    monkeypatch.setattr(
        storage, "get_snapshot_path", lambda: str(tmp_path / "snapshot_test.jpg")
    )

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    path = storage.save_snapshot(frame)
    assert os.path.exists(path)
