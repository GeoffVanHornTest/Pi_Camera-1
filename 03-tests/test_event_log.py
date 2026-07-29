import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import event_log


@pytest.fixture(autouse=True)
def tmp_log(tmp_path):
    """Give each test its own fresh log file.

    Session-level redirection away from the real log is handled by
    conftest.py; this fixture just points the logger at a per-test
    temp file so tests don't share state with each other.
    """
    log_file = str(tmp_path / "test_events.log")
    event_log._init(log_file)
    yield log_file


def _read_log(log_file):
    with open(log_file) as f:
        return f.read()


def test_log_creates_file(tmp_log):
    event_log.log("STARTUP", "test run")
    assert os.path.exists(tmp_log)


def test_log_contains_event_type(tmp_log):
    event_log.log("MOTION", "Recording started → 00-clips/motion.mp4")
    content = _read_log(tmp_log)
    assert "MOTION" in content


def test_log_contains_detail(tmp_log):
    event_log.log("UPLOAD_OK", "https://dropbox.com/s/abc123/clip.mp4")
    content = _read_log(tmp_log)
    assert "https://dropbox.com/s/abc123/clip.mp4" in content


def test_log_without_detail(tmp_log):
    event_log.log("SHUTDOWN")
    content = _read_log(tmp_log)
    assert "SHUTDOWN" in content


def test_log_appends_multiple_lines(tmp_log):
    event_log.log("STARTUP", "started")
    event_log.log("MOTION", "clip started")
    event_log.log("STOP", "recording stopped")
    content = _read_log(tmp_log)
    assert content.count("\n") == 3


def test_log_format_has_timestamp_and_separator(tmp_log):
    event_log.log("TELEGRAM_OK", "Photo sent: snapshot.jpg")
    line = _read_log(tmp_log).strip()
    # expect: "YYYY-MM-DD HH:MM:SS | TELEGRAM_OK   | Photo sent: snapshot.jpg"
    parts = line.split(" | ")
    assert len(parts) == 3
    assert parts[1].strip() == "TELEGRAM_OK"
    assert "Photo sent" in parts[2]


def test_log_event_type_is_left_padded(tmp_log):
    event_log.log("STOP", "done")
    line = _read_log(tmp_log).strip()
    # event type field is 14 chars wide — "STOP" + 10 spaces before " | "
    after_timestamp = line.split(" | ", 1)[1]  # "STOP           | done"
    assert after_timestamp.startswith("STOP")
    assert " | " in after_timestamp


def test_log_file_is_in_05_logs():
    import config
    assert "05-logs" in config.LOG_FILE


def test_log_file_is_string():
    import config
    assert isinstance(config.LOG_FILE, str)