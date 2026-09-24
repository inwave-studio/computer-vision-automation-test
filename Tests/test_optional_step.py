"""An optional waitUntil that never comes true must not fail the testcase."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoplay import *  # noqa: E402,F403

missing = waitUntil(
    lambda: findText("a screen that does not exist"),
    timeout=2_000,
    label="popup that never shows",
    required=False,
)

alert(missing is None, name="optional wait returned None instead of failing")
