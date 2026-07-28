import importlib
import json
import math
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


# --- Override layer crash-path tests (#110) ---


def test_non_dict_json_uses_defaults(tmp_path, monkeypatch, restore_config):
    """A top-level JSON array leaves all constants at their defaults."""
    overrides = tmp_path / "overrides.json"
    overrides.write_text("[]")
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert config.SCENE_CHANGE_THRESHOLD == 15.0


def test_zero_numeric_override_not_applied(tmp_path, monkeypatch, restore_config):
    """A zero value for a numeric constant is silently ignored."""
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"FPS": 0}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert config.FPS > 0


def test_negative_numeric_override_not_applied(tmp_path, monkeypatch, restore_config):
    """A negative value for a numeric constant is silently ignored."""
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"SCENE_CHANGE_WINDOW_SEC": -1}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert config.SCENE_CHANGE_WINDOW_SEC > 0


def test_project_tree_clips_dir_rejected(tmp_path, monkeypatch, restore_config):
    """Any CLIPS_DIR that resolves into the project tree is silently ignored.

    The guard now blocks the entire _BASE_DIR tree rather than specific
    subdirs — covers source files, .env, config overrides, and new dirs.
    """
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "02-scripts")
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"CLIPS_DIR": scripts_dir}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    original = config.CLIPS_DIR
    importlib.reload(config)
    assert config.CLIPS_DIR == original


def test_dotenv_as_log_file_rejected(tmp_path, monkeypatch, restore_config):
    """LOG_FILE pointing at .env is rejected — log rotation would destroy credentials."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"LOG_FILE": env_path}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    original = config.LOG_FILE
    importlib.reload(config)
    assert config.LOG_FILE == original


def test_relative_dot_clips_dir_rejected(tmp_path, monkeypatch, restore_config):
    """A relative CLIPS_DIR of '.' resolves to the project root and is rejected."""
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"CLIPS_DIR": "."}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    original = config.CLIPS_DIR
    importlib.reload(config)
    assert config.CLIPS_DIR == original


def test_home_dir_root_clips_dir_rejected(tmp_path, monkeypatch, restore_config):
    """CLIPS_DIR set to the home directory root is rejected.

    cleanup_old_clips() has no extension filter; setting CLIPS_DIR to the
    home root would delete arbitrary personal files after 7 days.
    """
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"CLIPS_DIR": os.path.expanduser("~")}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    original = config.CLIPS_DIR
    importlib.reload(config)
    assert config.CLIPS_DIR == original


def test_system_dir_clips_dir_rejected(tmp_path, monkeypatch, restore_config):
    """Paths outside the allowlist (home/media/mnt) are silently ignored.

    /var/log is representative of the full class — /tmp, /opt, /proc, /etc,
    and any other path not under ~/…, /media/…, or /mnt/… are all rejected
    by the allowlist check without needing to enumerate them individually.
    """
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"CLIPS_DIR": "/var/log"}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    original = config.CLIPS_DIR
    importlib.reload(config)
    assert config.CLIPS_DIR == original


def test_home_hidden_dir_clips_dir_rejected(tmp_path, monkeypatch, restore_config):
    """CLIPS_DIR pointing at a hidden home subdirectory is rejected.

    cleanup_old_clips() has no extension filter — ~/.ssh as CLIPS_DIR would
    delete all SSH keys older than 7 days. The hidden-component check catches
    ~/.ssh, ~/.gnupg, ~/.aws, ~/.config, and any future dot-dirs.
    """
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"CLIPS_DIR": os.path.expanduser("~/.ssh")}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    original = config.CLIPS_DIR
    importlib.reload(config)
    assert config.CLIPS_DIR == original


def test_media_path_clips_dir_accepted(tmp_path, monkeypatch, restore_config):
    """A CLIPS_DIR under /media (external drive) is accepted when the directory exists.

    /media is a primary legitimate target for Pi camera storage — external
    USB drives and SD cards mount there. The existence guard must not block it.
    isdir/islink are monkeypatched to simulate a mounted USB drive without
    requiring physical hardware.
    """
    target = "/media/pi/usb0/clips"
    real_isdir = os.path.isdir
    real_islink = os.path.islink
    monkeypatch.setattr(os.path, "isdir", lambda p: True if p == target else real_isdir(p))
    monkeypatch.setattr(os.path, "islink", lambda p: False if p == target else real_islink(p))
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"CLIPS_DIR": target}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert config.CLIPS_DIR == target


def test_home_subdir_clips_dir_accepted(tmp_path, monkeypatch, restore_config):
    """A plain (non-hidden) home subdirectory that exists is accepted.

    ~/clips is the simplest legitimate target — must pass the allowlist,
    the hidden-component check, and the new existence guard (TOCTOU fix).
    tmp_path is used as the mock home directory so the test is hermetic.
    """
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    real_expanduser = os.path.expanduser
    monkeypatch.setattr(
        os.path, "expanduser",
        lambda p: str(tmp_path) if p == "~" else real_expanduser(p),
    )
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"CLIPS_DIR": str(clips_dir)}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert config.CLIPS_DIR == str(clips_dir)


def test_nonexistent_clips_dir_rejected(tmp_path, monkeypatch, restore_config):
    """A CLIPS_DIR path that does not exist on disk is rejected (TOCTOU guard).

    realpath() cannot resolve a non-existent path — it returns the bare string.
    A symlink created at that location after config load would bypass all
    validation. Requiring existence at load time closes the TOCTOU window:
    the GUI must create the directory before writing the override.
    Uses tmp_path so the non-existent subdir is guaranteed not to exist
    and no real home directory path is hard-coded (#145).
    """
    target = str(tmp_path / "nonexistent_subdir")  # pytest never creates this subdir
    real_expanduser = os.path.expanduser
    monkeypatch.setattr(
        os.path, "expanduser",
        lambda p: str(tmp_path) if p == "~" else real_expanduser(p),
    )
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"CLIPS_DIR": target}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    original = config.CLIPS_DIR
    importlib.reload(config)
    assert config.CLIPS_DIR == original


def test_overflow_int_override_not_applied(tmp_path, monkeypatch, restore_config):
    """1e999 on an int constant raises OverflowError at int() — kept default."""
    overrides = tmp_path / "overrides.json"
    overrides.write_text('{"FPS": 1e999}')
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)  # must not raise
    assert config.FPS > 0


def test_inf_float_override_not_applied(tmp_path, monkeypatch, restore_config):
    """1e999 on a float constant silently produces float('inf') — must be rejected.

    float(float('inf')) does not raise, so OverflowError alone is insufficient.
    float('inf') as SCENE_CHANGE_THRESHOLD makes every gate comparison False,
    silently disabling the entire scene-change feature.
    """
    overrides = tmp_path / "overrides.json"
    overrides.write_text('{"SCENE_CHANGE_THRESHOLD": 1e999}')
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert math.isfinite(config.SCENE_CHANGE_THRESHOLD)


def test_nan_float_override_not_applied(tmp_path, monkeypatch, restore_config):
    """A string 'nan' coerces to float('nan') via float() — must be rejected.

    float('nan') as SCENE_CHANGE_THRESHOLD makes every gate comparison False,
    silently disabling the entire scene-change feature.
    """
    overrides = tmp_path / "overrides.json"
    overrides.write_text('{"SCENE_CHANGE_THRESHOLD": "nan"}')
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert math.isfinite(config.SCENE_CHANGE_THRESHOLD)


def test_non_scalar_override_not_applied(tmp_path, monkeypatch, restore_config):
    """A non-scalar constant (tuple RESOLUTION) is silently skipped.

    type(tuple)("640x480") produces ('6','4','0','x','4','8','0') with no
    exception — the guard must reject it before coercion is attempted.
    """
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"RESOLUTION": "640x480"}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    original = config.RESOLUTION
    importlib.reload(config)
    assert config.RESOLUTION == original


def test_out_of_range_fraction_override_not_applied(tmp_path, monkeypatch, restore_config):
    """A fraction constant overridden outside (0, 1) is silently ignored.

    MIN_BLOB_COHERENCE=50.0 passes the >0 guard but permanently disables
    motion detection since no blob coherence value can reach 50.0.
    """
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"MIN_BLOB_COHERENCE": 50.0}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert 0 < config.MIN_BLOB_COHERENCE < 1


# --- #138: islink dead code + LOG_FILE isdir() mis-validation ---


def test_symlink_clips_dir_rejected(tmp_path, monkeypatch, restore_config):
    """A CLIPS_DIR that is a symlink in the input path is rejected before realpath().

    realpath() resolves all symlink components, so islink() on its result is always
    False. The check must happen on the original (pre-realpath) path (#138).
    """
    real_dir = tmp_path / "real_clips"
    real_dir.mkdir()
    link_path = tmp_path / "clips_link"
    link_path.symlink_to(real_dir)
    real_expanduser = os.path.expanduser
    monkeypatch.setattr(
        os.path, "expanduser",
        lambda p: str(tmp_path) if p == "~" else real_expanduser(p),
    )
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"CLIPS_DIR": str(link_path)}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    original = config.CLIPS_DIR
    importlib.reload(config)
    assert config.CLIPS_DIR == original, (
        "symlink CLIPS_DIR was accepted — islink() must be checked on the raw input path"
    )


def test_log_file_valid_path_accepted(tmp_path, monkeypatch, restore_config):
    """A LOG_FILE override with a valid file path under ~/logs/ is accepted.

    LOG_FILE expects a file path, not a directory. The parent directory must
    exist; the file itself need not. The old isdir() guard rejected all valid
    LOG_FILE overrides because isdir() returns False for file paths (#138).
    """
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    log_file = logs_dir / "camera.log"  # file does not exist yet — RotatingFileHandler creates it
    real_expanduser = os.path.expanduser
    monkeypatch.setattr(
        os.path, "expanduser",
        lambda p: str(tmp_path) if p == "~" else real_expanduser(p),
    )
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"LOG_FILE": str(log_file)}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert config.LOG_FILE == str(log_file), (
        "valid LOG_FILE path was rejected — parent-directory check must accept file paths"
    )


def test_log_file_directory_path_rejected(tmp_path, monkeypatch, restore_config):
    """A LOG_FILE override pointing at an existing directory is rejected.

    If accepted, RotatingFileHandler raises IsADirectoryError on every write,
    silently disabling logging for the process lifetime (#138).
    """
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    real_expanduser = os.path.expanduser
    monkeypatch.setattr(
        os.path, "expanduser",
        lambda p: str(tmp_path) if p == "~" else real_expanduser(p),
    )
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"LOG_FILE": str(logs_dir)}))  # directory, not file
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    original = config.LOG_FILE
    importlib.reload(config)
    assert config.LOG_FILE == original, (
        "directory path accepted as LOG_FILE — must reject paths where dirname == path"
    )


# --- #139: _home realpath normalization ---


def test_home_symlink_clips_dir_accepted(tmp_path, monkeypatch, restore_config):
    """CLIPS_DIR under a realpath-resolved home dir is accepted on symlinked-/home systems.

    expanduser('~') may return a path with unresolved symlinks (e.g. /home/pi when
    /home -> /var/home). Without realpath() on _home, the allowlist comparison fails
    asymmetrically and all home-directory overrides are silently rejected (#139).
    """
    real_home = tmp_path / "real_home"
    real_home.mkdir()
    symlinked_home = tmp_path / "home_link"
    symlinked_home.symlink_to(real_home)
    clips_dir = real_home / "clips"
    clips_dir.mkdir()
    real_expanduser = os.path.expanduser
    monkeypatch.setattr(
        os.path, "expanduser",
        lambda p: str(symlinked_home) if p == "~" else real_expanduser(p),
    )
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"CLIPS_DIR": str(clips_dir)}))
    monkeypatch.setenv("_PI_CAMERA_OVERRIDES_PATH", str(overrides))
    importlib.reload(config)
    assert config.CLIPS_DIR == str(clips_dir), (
        "CLIPS_DIR under realpath-resolved home rejected — "
        "_home must use realpath(expanduser('~')) for consistent comparison"
    )
