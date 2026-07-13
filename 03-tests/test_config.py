import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import config


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
    assert config.MOTION_THRESHOLD_NIGHT > config.MOTION_THRESHOLD_DAY


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
