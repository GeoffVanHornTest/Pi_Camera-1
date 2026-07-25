import importlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import config
import pytest


def test_resolution_is_tuple():
    assert isinstance(config.RESOLUTION, tuple)


def test_resolution_has_two_dimensions():
    assert len(config.RESOLUTION) == 2


def test_resolution_values_are_positive():
    width, height = config.RESOLUTION
    assert width > 0
    assert height > 0


def test_fps_is_positive():
    assert config.FPS > 0


def test_motion_threshold_is_positive():
    assert config.MOTION_THRESHOLD_DAY > 0
    assert config.MOTION_THRESHOLD_NIGHT > 0


def test_motion_cooldown_is_positive():
    assert config.MOTION_COOLDOWN_SEC > 0


def test_post_motion_buffer_is_positive():
    assert config.POST_MOTION_BUFFER_SEC > 0


def test_notification_cooldown_is_positive():
    assert config.NOTIFICATION_COOLDOWN_SEC > 0


def test_clips_dir_is_string():
    assert isinstance(config.CLIPS_DIR, str)


def test_notification_cooldown_longer_than_motion_cooldown():
    # Email cooldown should always be >= motion cooldown to avoid alert flooding
    assert config.NOTIFICATION_COOLDOWN_SEC >= config.MOTION_COOLDOWN_SEC


def test_min_consecutive_frames_is_positive_int():
    assert isinstance(config.MIN_CONSECUTIVE_FRAMES, int)
    assert config.MIN_CONSECUTIVE_FRAMES >= 1


def test_min_blob_coherence_is_valid_fraction():
    assert 0.0 < config.MIN_BLOB_COHERENCE < 1.0


def test_centroid_history_len_is_positive_int():
    assert isinstance(config.CENTROID_HISTORY_LEN, int)
    assert config.CENTROID_HISTORY_LEN >= 1


def test_scene_change_window_sec_is_positive():
    assert config.SCENE_CHANGE_WINDOW_SEC > 0


def test_scene_change_window_frames_derived_from_sec_and_fps():
    assert config.SCENE_CHANGE_WINDOW_FRAMES == config.SCENE_CHANGE_WINDOW_SEC * config.FPS


def test_scene_change_threshold_is_positive():
    assert config.SCENE_CHANGE_THRESHOLD > 0


def test_scene_change_suppress_sec_is_positive():
    assert config.SCENE_CHANGE_SUPPRESS_SEC > 0


# --- Override layer tests (#102) ---


@pytest.fixture
def restore_config():
    """Reload config to defaults after a test that calls importlib.reload(config)."""
    yield
    os.environ.pop("_PI_CAMERA_OVERRIDES_PATH", None)
    importlib.reload(config)


def test_valid_override_applies(tmp_path, monkeypatch, restore_config):
    """A valid JSON override changes the named config constant."""
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"SCENE_CHANGE_THRESHOLD": 42.0}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert config.SCENE_CHANGE_THRESHOLD == 42.0


def test_missing_overrides_file_uses_defaults(monkeypatch, restore_config):
    """A nonexistent overrides path leaves all constants at their defaults."""
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", "/nonexistent/overrides.json")
    importlib.reload(config)
    assert config.SCENE_CHANGE_THRESHOLD == 15.0


def test_malformed_json_uses_defaults(tmp_path, monkeypatch, restore_config):
    """Malformed JSON in the overrides file leaves constants at their defaults."""
    overrides = tmp_path / "overrides.json"
    overrides.write_text("{not: valid json}")
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert config.SCENE_CHANGE_THRESHOLD == 15.0


def test_credential_key_not_overridable(tmp_path, monkeypatch, restore_config):
    """Credential keys in the overrides file are silently ignored."""
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"TELEGRAM_BOT_TOKEN": "leaked_token_123"}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert config.TELEGRAM_BOT_TOKEN != "leaked_token_123"
