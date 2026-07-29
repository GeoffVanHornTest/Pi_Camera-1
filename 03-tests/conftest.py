import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import event_log


@pytest.fixture(autouse=True, scope="session")
def isolate_event_log(tmp_path_factory):
    """Redirect event_log to a temp file for the entire test session.

    Prevents test runs from writing fabricated entries (fake STARTUP, ERROR,
    FATAL, URLs) into the real 05-logs/pi_camera.log, which exists for
    post-hoc production troubleshooting.
    """
    log_file = str(tmp_path_factory.mktemp("logs") / "test_events.log")
    event_log._init(log_file)
    yield log_file