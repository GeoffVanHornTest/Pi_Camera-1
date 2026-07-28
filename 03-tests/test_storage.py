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


# --- #143: PermissionError in cleanup must not propagate ---


def test_cleanup_permission_error_does_not_raise(tmp_path, monkeypatch):
    """cleanup_old_clips() must not propagate PermissionError from os.remove().

    A read-only filesystem after unclean SD-card power loss raises PermissionError
    on every os.remove() call. Previously this propagated into main()'s consecutive-
    error handler and killed the service after 10 iterations (#143).
    """
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    old_file = tmp_path / "motion_old.mp4"
    old_file.write_text("x")
    old_time = __import__("time").time() - (8 * 86400)
    __import__("os").utime(str(old_file), (old_time, old_time))

    def raise_permission(path):
        raise PermissionError(f"read-only filesystem: {path}")

    monkeypatch.setattr(storage.os, "remove", raise_permission)
    storage.cleanup_old_clips(days=7)  # must not raise


# --- #144: cleanup must not delete non-.mp4/.jpg files ---


def test_cleanup_preserves_non_output_files(tmp_path, monkeypatch):
    """cleanup_old_clips() must not delete files that storage.py did not create.

    Only .mp4 clips and .jpg snapshots are managed. Operator notes, lock files,
    pid files, and any other extension must be left untouched (#144).
    """
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    old_time = __import__("time").time() - (8 * 86400)
    for name in ("notes.txt", "camera.pid", "backup.conf", "data.csv"):
        f = tmp_path / name
        f.write_text("x")
        __import__("os").utime(str(f), (old_time, old_time))

    storage.cleanup_old_clips(days=7)

    for name in ("notes.txt", "camera.pid", "backup.conf", "data.csv"):
        assert (tmp_path / name).exists(), f"{name} was deleted — only .mp4/.jpg should be removed"


def test_cleanup_deletes_old_mp4_and_jpg(tmp_path, monkeypatch):
    """cleanup_old_clips() must delete .mp4 and .jpg files older than the retention period."""
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(tmp_path))
    old_time = __import__("time").time() - (8 * 86400)
    old_mp4 = tmp_path / "motion_old.mp4"
    old_jpg = tmp_path / "snapshot_old.jpg"
    old_mp4.write_text("x")
    old_jpg.write_text("x")
    __import__("os").utime(str(old_mp4), (old_time, old_time))
    __import__("os").utime(str(old_jpg), (old_time, old_time))

    storage.cleanup_old_clips(days=7)

    assert not old_mp4.exists(), "old .mp4 was not deleted"
    assert not old_jpg.exists(), "old .jpg was not deleted"


# --- #147: TOCTOU — cleanup must re-validate CLIPS_DIR before file operations ---


def test_cleanup_raises_if_clips_dir_no_longer_exists(tmp_path, monkeypatch):
    """cleanup_old_clips() must raise RuntimeError if CLIPS_DIR has been removed.

    The directory is validated at config-load time but the filesystem can change
    while the service is running. Re-checking before each cleanup prevents file
    operations on a path that no longer exists as a real directory (#147).
    """
    vanished = tmp_path / "vanished_clips"
    vanished.mkdir()
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(vanished))
    vanished.rmdir()  # simulate directory disappearing after config loaded

    with pytest.raises(RuntimeError, match="no longer exists"):
        storage.cleanup_old_clips(days=7)


def test_cleanup_raises_if_clips_dir_replaced_by_symlink(tmp_path, monkeypatch):
    """cleanup_old_clips() must raise RuntimeError if CLIPS_DIR is now a symlink.

    An attacker with local write access could replace the validated directory with
    a symlink (e.g. ln -s ~/.ssh /home/pi/safe_clips) after config loads. Without
    re-validation, cleanup's os.remove() would delete files from the symlink target.
    config.CLIPS_DIR is stored as a realpath() result; if realpath() now differs,
    the path has been replaced (#147).
    """
    real_dir = tmp_path / "real_clips"
    real_dir.mkdir()
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    monkeypatch.setattr(storage.config, "CLIPS_DIR", str(clips_dir))
    # Replace the real directory with a symlink after config "loaded"
    clips_dir.rmdir()
    clips_dir.symlink_to(real_dir)

    with pytest.raises(RuntimeError, match="replaced by a symlink"):
        storage.cleanup_old_clips(days=7)
