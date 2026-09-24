"""auto-play: write Android UI testcases as plain Python scripts.

    from autoplay import *

    app_id = "com.amanotes.beathopper"
    kill(app_id); clear(app_id); open_app(app_id)
    waitUntil(lambda: find("welcome-screen") or findText("notifications?"))

The module-level functions run against one implicit Session, created on first
use so a testcase never has to manage setup or teardown itself.
"""

import os
import sys

from .device import AdbError, Device
from .log import step
from .screen import Screen, ScreenError
from .session import (
    AD_APPEAR_TIMEOUT,
    AD_CLOSE_TIMEOUT,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    Position,
    Session,
    TestFailure,
    load_database,
    norm,
)
from .vision import Element, TemplateMatcher, TextFinder

__all__ = [
    "alert",
    "clear",
    "closeAd",
    "doubleTap",
    "find",
    "findLayout",
    "findText",
    "hide",
    "isAdShowing",
    "kill",
    "multiTap",
    "norm",
    "open_app",
    "readText",
    "scrollHorizontal",
    "scrollVerticle",
    "scrollVertical",
    "stop",
    "tap",
    "wait",
    "waitForAd",
    "waitUntil",
    "session",
    "configure",
    "Position",
    "Session",
    "Element",
    "TestFailure",
    "AdbError",
]

_session = None
_config = {}


def configure(**kwargs):
    """Set Session options (serial, database, base_dir, testcase) before first use."""
    if _session is not None:
        raise RuntimeError("configure() must be called before any other auto-play API")
    _config.update(kwargs)


def session():
    """The implicit Session, created on first use."""
    global _session
    if _session is None:
        config = dict(_config)
        config.setdefault("base_dir", _testcase_dir())
        _session = Session(**config)
    return _session


def _testcase_dir():
    main = sys.modules.get("__main__")
    path = getattr(main, "__file__", None)
    return os.path.dirname(os.path.abspath(path)) if path else os.getcwd()


def alert(expression, name=None):
    return session().alert(expression, name=name)


def clear(app_id):
    return session().clear(app_id)


def open_app(app_id):
    return session().open(app_id)


# The design calls this `open`. Exposed as `autoplay.open(...)` but deliberately
# kept out of __all__ so `from autoplay import *` does not shadow the builtin.
open = open_app


def kill(app_id):
    return session().kill(app_id)


def stop(app_id):
    return session().stop(app_id)


def hide(app_id):
    return session().hide(app_id)


def tap(element):
    return session().tap(element)


def doubleTap(element):
    return session().doubleTap(element)


def multiTap(target, *args, offset=None, count=None, duration=None):
    return session().multiTap(
        target, *args, offset=offset, count=count, duration=duration
    )


def readText(element):
    return session().readText(element)


def find(pattern, retries=None, *, threshold=None):
    return session().find(pattern, retries=retries, threshold=threshold)


def findLayout(pattern, retries=None, *, threshold=None):
    return session().findLayout(pattern, retries=retries, threshold=threshold)


def findText(needle, retries=None, case_sensitive=False):
    return session().findText(needle, retries=retries, case_sensitive=case_sensitive)


def isAdShowing(patterns=None):
    return session().isAdShowing(patterns=patterns)


def waitForAd(timeout=AD_APPEAR_TIMEOUT, patterns=None, required=False):
    return session().waitForAd(timeout=timeout, patterns=patterns, required=required)


def closeAd(timeout=AD_CLOSE_TIMEOUT, patterns=None, close_ids=None, required=True):
    return session().closeAd(
        timeout=timeout, patterns=patterns, close_ids=close_ids, required=required
    )


def waitUntil(expression, timeout=DEFAULT_TIMEOUT, label=None, required=True):
    return session().waitUntil(
        expression, timeout=timeout, label=label, required=required
    )


def wait(milliseconds):
    return session().wait(milliseconds)


def scrollVerticle(percent_of_screen_height, duration_ms=400):
    return session().scrollVerticle(percent_of_screen_height, duration_ms)


scrollVertical = scrollVerticle


def scrollHorizontal(percent_of_screen_width, duration_ms=400):
    return session().scrollHorizontal(percent_of_screen_width, duration_ms)
