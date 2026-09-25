"""The auto-play session: holds the device, the screen stream and the vision
stack, and exposes the testcase API described in .agent/design.md."""

import atexit
import importlib.util
import os
import sys
import time

from .ads import AD_ACTIVITY_PATTERNS, activity_class, looks_like_ad
from .device import Device
from .log import recorder, result, skipped, step, summary
from .screen import Screen
from .vision import MODE_EDGE, MODE_TEMPLATE, Element, TemplateMatcher, TextFinder

DEFAULT_TIMEOUT = 10_000  # ms
POLL_INTERVAL = 0.25  # s

# -- ads ------------------------------------------------------------------
# How long to wait for an ad to turn up after the action that should trigger
# one. Generous because an interstitial is fetched over the network the moment
# it is asked for, and a cold cache on a slow connection is seconds.
AD_APPEAR_TIMEOUT = 15_000  # ms
# How long an ad may take to become closable. A rewarded video is commonly 30s
# and the close control only appears at the end of it, so this has to outlast
# the longest ad the app serves rather than the longest one usually seen.
AD_CLOSE_TIMEOUT = 90_000  # ms
# Each poll is an adb round-trip (~120ms) plus a template match, so this is the
# gap between polls and not the poll rate.
AD_POLL_INTERVAL = 0.5  # s
# After tapping a close control, how long to let the SDK tear the activity down
# before asking again - without this the same close is tapped two or three
# times, and the extra taps land on whatever the app shows next.
AD_AFTER_TAP = 1.0  # s
# Element-database ids tried, in order, to find an ad's close button. Missing
# ids are skipped, so a project that defines none still works on the text
# fallback below.
AD_CLOSE_IDS = ("ad-close", "ad-skip", "close-popup")
# Text a close control carries when there is no template for it. Matched
# case-insensitively as substrings, so "Skip Ad" and "SKIP" both hit "skip".
AD_CLOSE_WORDS = ("skip ad", "skip", "close", "continue", "đóng", "bỏ qua")

# A lookup that comes up empty is retried this many extra times, 100ms apart
# (design.md task 4). A screen mid-transition is the common case: the frame that
# was grabbed is a fade or a half-finished slide, and the element is plainly
# there 100ms later.
DEFAULT_RETRIES = 3
RETRY_DELAY = 100  # ms between attempts


class TestFailure(AssertionError):
    """Raised to stop auto-play when a testcase fails."""


class Position:
    """A point given as a fraction of the screen, not in pixels.

    The origin is the top-left corner, x grows to the right and y downwards, so
    `Position(0.5, 0.25)` is the middle of the screen a quarter of the way down
    (design.md task 8). Resolution-independent, so the same testcase works on
    any device.
    """

    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)

    def to_device(self, width, height):
        return (
            _clamp(round(self.x * width), 0, width - 1),
            _clamp(round(self.y * height), 0, height - 1),
        )

    def __iter__(self):
        return iter((self.x, self.y))

    def __repr__(self):
        return f"norm({self.x:g},{self.y:g})"


def norm(x, y=None):
    """A normalized screen position: `norm(0.5, 0.9)` or `norm((0.5, 0.9))`.

    `tap` and `multiTap` also accept a bare `(0.5, 0.9)` tuple - a pair of
    floats inside 0..1 is read as normalized - but `norm()` says so outright,
    which matters at the edges where `(0, 0)` and `(1, 1)` are ambiguous.
    """
    if y is None:
        x, y = x
    return Position(x, y)


def _as_position(value):
    """Read `value` as a normalized position, or return None.

    A pair of `float`s within 0..1 is taken as normalized; ints are pixels. That
    keeps `tap((540, 1200))` meaning pixels and `tap((0.5, 0.5))` meaning the
    middle of the screen, which is what each of them looks like it means.
    """
    if isinstance(value, Position):
        return value
    if isinstance(value, (list, tuple)) and len(value) == 2:
        if all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in value):
            return Position(*value)
    return None


class Session:
    def __init__(self, serial=None, database=None, base_dir=None, testcase=None):
        self.base_dir = base_dir or os.getcwd()
        self.testcase = testcase or _caller_testcase()
        if database is not None:
            self.database, self.db_dir = database, self.base_dir
        else:
            self.database, self.db_dir = find_database(self.base_dir)

        step(f"session: starting testcase '{self.testcase}'")
        self.device = Device(serial=serial)
        step(f"session: device {self.device.serial} ({self.device.width}x{self.device.height})")

        self.screen = Screen(self.device)
        self.screen.start()

        self.matcher = TemplateMatcher(self.database, base_dir=self.db_dir)
        self.text = TextFinder()

        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.aborted = None
        self._frame_at = None
        self._last_frame = None
        self._polling = False
        self._closed = False
        atexit.register(self.close)

    # -- frames ----------------------------------------------------------

    def frame(self, fresh=False):
        """The newest screen frame, timestamped for the reaction clock."""
        image = self.screen.latest(max_age=1.0 if fresh else 0.0)
        self._frame_at = time.perf_counter()
        # Kept so a snapshot pictures the frame the step actually decided on.
        # Re-grabbing at report time would show a screen that has since moved,
        # which is the one thing a failure screenshot must not do.
        self._last_frame = image
        return image

    def _snap(self, tag, boxes=(), sought=(), frame=None, force=False):
        """Attach a screenshot to the step just logged, when recording.

        `sought` names the element ids that were being looked for, and their
        template images are put beside the screen. The ids are resolved here
        rather than by the caller so that a run without a report - the common
        case - does no database or path work at all.

        A lookup inside a poll loop takes no picture unless `force`: every poll
        grabs a new frame, so a 10s waitUntil would otherwise leave a dozen
        near-identical shots of the screen not having changed yet. waitUntil
        forces its own, once, of the frame that settled it - which is the one
        worth looking at.
        """
        rec = recorder()
        if rec is None or (self._polling and not force):
            return
        image = frame if frame is not None else self._last_frame
        templates = []
        for element_id in sought:
            templates.extend(self.matcher.template_files(element_id))
        rec.attach(**rec.snapshot(image, boxes, templates, tag))

    def _reaction(self):
        """How long since the frame this action is reacting to was grabbed.

        design.md task 3 asks for the time from taking a screen frame to
        issuing the device command for each step. That span is what decides
        whether a tap can land on what the frame showed, so every input logs
        it - it is the number to watch when a tap starts missing a moving
        target. Frame age inside the stream is on top of it, not included.
        """
        if self._frame_at is None:
            return ""
        return f"  [{(time.perf_counter() - self._frame_at) * 1000:.0f}ms since frame]"

    # -- retrying --------------------------------------------------------

    def _tries(self, retries):
        """Yield (attempt, total) for a lookup, pausing RETRY_DELAY between them.

        `retries=None` means "decide for me": normally DEFAULT_RETRIES, but none
        at all while waitUntil is polling. Inside a poll loop the retry would be
        redundant and actively harmful - waitUntil already re-runs the
        expression, and an OCR pass costs about a second, so four attempts per
        poll turn a 2s optional wait into a single 4s attempt. An explicit
        `retries=` is always honoured, wherever it is called from.
        """
        if retries is None:
            retries = 0 if self._polling else DEFAULT_RETRIES
        total = max(1, int(retries) + 1)
        for attempt in range(1, total + 1):
            if attempt > 1:
                time.sleep(RETRY_DELAY / 1000.0)
            yield attempt, total

    @staticmethod
    def _attempt_note(attempt, total):
        if total == 1 or attempt == 1:
            return ""
        return f" (attempt {attempt}/{total})"

    @staticmethod
    def _gave_up_note(total):
        return "" if total == 1 else f" after {total} attempts"

    # -- app lifecycle ---------------------------------------------------

    def open(self, app_id):
        step(f"open({app_id}): launching app")
        self.device.open_app(app_id)
        return self

    def kill(self, app_id):
        step(f"kill({app_id}): force-stopping app")
        self.device.kill_app(app_id)
        return self

    # `stop` is the name used in the sample script; keep both.
    stop = kill

    def clear(self, app_id):
        step(f"clear({app_id}): clearing app storage")
        self.device.clear_app(app_id)
        return self

    def hide(self, app_id):
        step(f"hide({app_id}): sending app to background (HOME)")
        self.device.home()
        return self

    # -- finding ---------------------------------------------------------

    def find(self, pattern, retries=None, *, threshold=None, mode=MODE_TEMPLATE):
        """find(element_id) -> list[Element] (empty if absent).
        find([id, ...]) -> True if at least one of them is on screen.

        Retries a few times before giving up - see `_tries`.

        The second positional is `retries`, matching findText, and `threshold`
        is keyword-only. It was the other way round, which read as a trap: the
        documented signature said retries, every testcase was written that way,
        and `find("paywall", 0)` therefore asked for *threshold 0* - matching
        every position on screen, 1794 boxes for one popup, seven seconds per
        poll. `find("close-popup", 5)` asked for a threshold no score can
        reach and so could never match at all. Neither spelling is wrong
        enough to raise, so the order is what had to change."""
        if isinstance(pattern, (list, tuple, set)):
            return self._find_any(pattern, retries=retries, threshold=threshold, mode=mode)

        call = "findLayout" if mode == MODE_EDGE else "find"
        how = " by outline" if mode == MODE_EDGE else ""
        variants = self.matcher.variant_count(pattern)
        of = f" of {variants} variants" if variants > 1 else ""
        for attempt, total in self._tries(retries):
            screen = self.frame()
            elements = self.matcher.find(screen, pattern, threshold=threshold, mode=mode)
            if elements:
                spots = ", ".join(f"{e.center}" for e in elements[:4])
                more = "..." if len(elements) > 4 else ""
                step(
                    f"{call}('{pattern}'){how}: {len(elements)} match(es){of} at "
                    f"{spots}{more}{self._attempt_note(attempt, total)}"
                )
                self._snap(pattern, [e.bounds for e in elements[:8]], frame=screen)
                return elements
        step(f"{call}('{pattern}'){how}: no match{self._gave_up_note(total)}")
        # A miss is where the pictures earn their keep: the screen that was
        # searched, beside the template that was being looked for.
        self._snap(pattern, sought=[pattern], frame=screen)
        return []

    def findLayout(self, pattern, retries=None, *, threshold=None):
        """Like find(), but matches the element's outline rather than its pixels.

        Both sides are reduced to Canny edge maps before correlating, so colour,
        fill and artwork stop mattering and the shape carries the match
        (design.md task 8). Use it for a layout drawn differently per theme or
        over changing content - a card, a panel, a dialog frame - and use
        find() when the artwork itself is the thing to recognise.
        """
        return self.find(pattern, retries=retries, threshold=threshold, mode=MODE_EDGE)

    def _find_any(self, patterns, retries=None, *, threshold=None, mode=MODE_TEMPLATE):
        call = "findLayout" if mode == MODE_EDGE else "find"
        patterns = list(patterns)
        for attempt, total in self._tries(retries):
            screen = self.frame()
            for pattern in patterns:
                if self.matcher.find(
                    screen, pattern, threshold=threshold, max_results=1, mode=mode
                ):
                    step(
                        f"{call}({patterns}): found '{pattern}'"
                        f"{self._attempt_note(attempt, total)}"
                    )
                    self._snap(pattern, frame=screen)
                    return True
        step(f"{call}({patterns}): none present{self._gave_up_note(total)}")
        self._snap("-".join(str(p) for p in patterns[:2]), sought=patterns, frame=screen)
        return False

    def findText(self, needle, retries=None, case_sensitive=False):
        """Find text on screen. Returns an Element or None.

        `needle` may also be a list of strings: the element carrying the first
        one of them that is on screen is returned, in the order given, so a
        label and its translations can be listed together (design.md task 5).

        Case is ignored by default, since OCR is not reliable about it. Pass
        `case_sensitive=True` when the difference is the point - telling an
        "OK" button from the word "ok" in a sentence beside it.
        """
        needles = [needle] if isinstance(needle, str) else list(needle)
        label = needle if isinstance(needle, str) else needles
        note = " case-sensitive" if case_sensitive else ""
        for attempt, total in self._tries(retries):
            element = self.text.find_any(self.frame(), needles, case_sensitive)
            if element:
                step(
                    f"findText({label!r}{note}): found {element.text!r}"
                    f" at {element.center}{self._attempt_note(attempt, total)}"
                )
                self._snap(needles[0], [element.bounds])
                return element
        step(f"findText({label!r}{note}): not found{self._gave_up_note(total)}")
        self._snap(needles[0] if needles else "text")
        return None

    def readText(self, element):
        """OCR the text inside an element's bounds."""
        screen = self.frame()
        x1, y1, x2, y2 = _clamp_bounds(_as_bounds(element), screen.shape)
        crop = screen[y1:y2, x1:x2]
        texts = [e.text for e in self.text.read_all(crop)]
        value = " ".join(texts).strip()
        step(f"readText({_describe(element)}): {value!r}")
        return value

    # -- input -----------------------------------------------------------

    def tap(self, element):
        x, y = self._point_on_device(element, "tap")
        step(f"tap({_describe(element)}): tapping ({x},{y}){self._reaction()}")
        self.device.tap(x, y)
        return (x, y)

    def doubleTap(self, element):
        x, y = self._point_on_device(element, "doubleTap")
        step(f"doubleTap({_describe(element)}): double-tapping ({x},{y}){self._reaction()}")
        self.device.double_tap(x, y)
        return (x, y)

    def multiTap(self, target, *args, offset=None, count=None, duration=None):
        """Tap the same spot several times (design.md task 8).

            multiTap(element, (dx, dy), count, duration_ms)
            multiTap(norm(x, y), count, duration_ms)

        `offset` shifts the point by (dx, dy) device pixels - positive y is
        downwards - so a tap can land next to what was matched rather than on
        its centre. `duration` is the whole gesture's span in ms, and the taps
        are spread evenly across it; leave it out for as fast as the device
        will go.

        The requested spacing is a floor, not a promise: each tap costs the
        device tens of ms to inject, so a duration shorter than `count` taps
        take is reported back as what actually happened rather than silently
        missed.
        """
        offset, count, duration = _multitap_args(target, args, offset, count, duration)
        x, y = self._point_on_device(target, "multiTap")
        dx, dy = (int(offset[0]), int(offset[1])) if offset else (0, 0)
        if dx or dy:
            x = _clamp(x + dx, 0, self.device.width - 1)
            y = _clamp(y + dy, 0, self.device.height - 1)
        # count-1 gaps span the duration: 3 taps over 200ms is one at 0, 100, 200.
        # `duration` is in ms, the device sleeps in seconds.
        interval = duration / 1000.0 / (count - 1) if duration and count > 1 else 0.0
        shift = f" offset ({dx},{dy})" if (dx or dy) else ""
        pace = f" over {duration}ms" if duration else " as fast as possible"
        step(
            f"multiTap({_describe(target)}){shift}: {count} taps at ({x},{y})"
            f"{pace}{self._reaction()}"
        )
        elapsed = self.device.multi_tap(x, y, count, interval)
        step(f"multiTap: {count} taps done in {elapsed:.0f}ms")
        return (x, y)

    def _point_on_device(self, element, method):
        """Resolve an element and convert its position to device pixels."""
        position = _as_position(element)
        if position is not None:
            return position.to_device(self.device.width, self.device.height)
        x, y = self._resolve_point(element, method)
        return self.screen.to_device(x, y)

    def _resolve_point(self, element, method):
        if element is None:
            raise TestFailure(f"{method}() called with None - the element was never found")
        if isinstance(element, Element):
            return element.center
        if isinstance(element, (list, tuple)):
            if not element:
                raise TestFailure(f"{method}() called with an empty match list")
            if isinstance(element[0], Element):
                return element[0].center
            if len(element) == 2:
                return int(element[0]), int(element[1])
        if isinstance(element, str):
            found = self.findText(element) or _first(self.find(element))
            if found is None:
                raise TestFailure(f"{method}('{element}') failed - not found on screen")
            return found.center
        raise TestFailure(f"{method}() cannot resolve {element!r} to a screen position")

    # -- scrolling -------------------------------------------------------

    def scrollVerticle(self, percent_of_screen_height, duration_ms=400):
        """Negative percent scrolls the content down (finger swipes up)."""
        w, h = self.device.width, self.device.height
        distance = int(h * percent_of_screen_height / 100.0)
        cx = w // 2
        # Centre the swipe on the screen. Negative distance must move the
        # finger UP (start low, end high) so the content scrolls down.
        start_y = _clamp(h // 2 - distance // 2, 1, h - 2)
        end_y = _clamp(start_y + distance, 1, h - 2)
        direction = "down" if percent_of_screen_height < 0 else "up"
        step(
            f"scrollVerticle({percent_of_screen_height}): scrolling {direction} "
            f"{abs(percent_of_screen_height)}% of height{self._reaction()}"
        )
        self.device.swipe(cx, start_y, cx, end_y, duration_ms)
        return self

    # Common misspelling-free alias.
    scrollVertical = scrollVerticle

    def scrollHorizontal(self, percent_of_screen_width, duration_ms=400):
        """Negative percent scrolls the content left (finger swipes right)."""
        w, h = self.device.width, self.device.height
        distance = int(w * percent_of_screen_width / 100.0)
        cy = h // 2
        start_x = _clamp(w // 2 + distance // 2, 1, w - 2)
        end_x = _clamp(start_x - distance, 1, w - 2)
        direction = "left" if percent_of_screen_width < 0 else "right"
        step(
            f"scrollHorizontal({percent_of_screen_width}): scrolling {direction} "
            f"{abs(percent_of_screen_width)}% of width{self._reaction()}"
        )
        self.device.swipe(start_x, cy, end_x, cy, duration_ms)
        return self

    # -- waiting ---------------------------------------------------------

    def waitUntil(self, expression, timeout=DEFAULT_TIMEOUT, label=None, required=True):
        """Poll `expression` until it is truthy and return its value.

        `required=True` (the default) means the step must happen: a timeout
        fails the testcase and stops auto-play. `required=False` marks an
        optional step - a step that only shows up sometimes, like a permission
        dialog or a promo popup. Then a timeout is not a failure: it returns
        None so the script can simply move on.
        """
        name = label or "condition"
        kind = "waiting" if required else "waiting (optional)"
        step(f"waitUntil({name}): {kind} up to {timeout}ms")
        deadline = time.time() + timeout / 1000.0
        attempts = 0
        while True:
            attempts += 1
            started = time.time()
            # The poll loop is the retry, so lookups inside it do not add their
            # own - see `_tries`.
            was_polling, self._polling = self._polling, True
            try:
                value = expression()
            finally:
                self._polling = was_polling
            # A poll cannot be interrupted once it is inside matchTemplate or
            # OCR, so a lookup slower than the whole timeout blows through it
            # and the wait looks hung - a 10s optional wait sat there for two
            # minutes with nothing on screen to explain why. The deadline still
            # cannot be enforced mid-poll, but an overrun is now said out loud,
            # which is the difference between a slow step and a hung one.
            overran = time.time() - started
            if overran > timeout / 1000.0:
                step(
                    f"waitUntil({name}): one check took {overran:.1f}s, longer than the "
                    f"{timeout}ms timeout - a lookup this slow cannot be polled"
                )
            if value:
                step(f"waitUntil({name}): satisfied after {attempts} check(s)")
                self._snap(name, [e.bounds for e in _elements(value)], force=True)
                return value
            if time.time() >= deadline:
                if not required:
                    self.skipped += 1
                    skipped(f"waitUntil({name})", f"not seen within {timeout}ms")
                    self._snap(name, force=True)
                    return None
                self.failed += 1
                result(f"waitUntil({name})", False, f"timed out after {timeout}ms")
                self._snap(name, force=True)
                raise TestFailure(f"waitUntil({name}) timed out after {timeout}ms")
            time.sleep(POLL_INTERVAL)

    def wait(self, milliseconds):
        step(f"wait({milliseconds}ms)")
        time.sleep(milliseconds / 1000.0)
        return self

    # -- ads -------------------------------------------------------------

    def isAdShowing(self, patterns=None):
        """True while a full-screen ad (interstitial or rewarded) is covering the app.

        Asks the device which activity has window focus and compares it against
        the known ad containers - see ads.py for why this is a window question
        and not a vision one. Costs about one adb round-trip (~120ms), so it is
        cheap enough to poll.

        `patterns=` replaces the built-in list for an ad network it does not
        know about; pass the lowercase class-name fragment to match.
        """
        patterns = tuple(patterns) if patterns else AD_ACTIVITY_PATTERNS
        activity = self.device.focused_activity()
        showing = looks_like_ad(activity, patterns)
        if showing:
            step(f"isAdShowing(): ad on screen - {activity_class(activity)}")
        else:
            step(f"isAdShowing(): no ad ({activity_class(activity) or 'unknown'} in front)")
        return showing

    def waitForAd(self, timeout=AD_APPEAR_TIMEOUT, patterns=None, required=False):
        """Wait for a full-screen ad to appear. Returns True if one did.

        Optional by default, unlike `waitUntil`: an ad that does not show is
        the normal case, not a broken testcase. Fill rate is not 100%, the
        cap is per-user and per-day, and a debug build often serves nothing at
        all - so a required-by-default version of this would fail runs for
        reasons that have nothing to do with the app.
        """
        patterns = tuple(patterns) if patterns else AD_ACTIVITY_PATTERNS
        step(f"waitForAd(): waiting up to {timeout}ms for an ad")
        deadline = time.time() + timeout / 1000.0
        while True:
            activity = self.device.focused_activity()
            if looks_like_ad(activity, patterns):
                step(f"waitForAd(): ad appeared - {activity_class(activity)}")
                self._snap("ad-appeared", force=True)
                return True
            if time.time() >= deadline:
                if required:
                    self.failed += 1
                    result("waitForAd()", False, f"no ad within {timeout}ms")
                    self._snap("ad-never-appeared", force=True)
                    raise TestFailure(f"waitForAd() timed out after {timeout}ms")
                self.skipped += 1
                skipped("waitForAd()", f"no ad within {timeout}ms")
                return False
            time.sleep(AD_POLL_INTERVAL)

    def closeAd(self, timeout=AD_CLOSE_TIMEOUT, patterns=None, close_ids=None, required=True):
        """Wait for the ad on screen to finish, close it, and return when it is gone.

        Returns True if an ad was closed, False if there was none to close.

        The two halves are deliberately different mechanisms. *Whether* an ad
        is up is read from the window - exact, no guessing. *How* to dismiss it
        is a vision problem: the close button appears only after a countdown,
        sits in a different corner per network, and is drawn as an x, a circled
        x, or the word Skip. So this polls the window for the ad to be gone,
        and meanwhile looks for anything tappable each time round.

        The back key is deliberately not used. Most ad SDKs swallow it until
        the reward is earned, and the ones that do not treat it as "user
        abandoned the ad", which is a different event from closing it and
        skews exactly the metrics an ad testcase exists to check.

        `close_ids=` names the element-database entries to try, in order;
        anything missing from the database is skipped rather than raising, so
        a project without ad-close templates still works on the text ones.
        """
        patterns = tuple(patterns) if patterns else AD_ACTIVITY_PATTERNS
        activity = self.device.focused_activity()
        if not looks_like_ad(activity, patterns):
            step("closeAd(): no ad on screen, nothing to close")
            return False

        step(f"closeAd(): {activity_class(activity)} up, waiting up to {timeout}ms for it to close")
        deadline = time.time() + timeout / 1000.0
        ids = list(close_ids) if close_ids is not None else list(AD_CLOSE_IDS)
        taps = 0
        while True:
            activity = self.device.focused_activity()
            # An empty read is "cannot tell", not "no ad". Measured on the test
            # device: every activity change is preceded by a poll where no
            # window holds focus at all, so a blank is exactly what a closing
            # *and* an opening ad look like mid-transition. Treating it as
            # closed would declare victory one poll early, while the ad is
            # still up - so wait for a window that actually names something.
            if activity and not looks_like_ad(activity, patterns):
                step(f"closeAd(): ad closed after {taps} tap(s)")
                self._snap("ad-closed", force=True)
                return True
            if time.time() >= deadline:
                break
            # Look for a way out. A miss is the normal state for most of an
            # ad's life - the close button is genuinely not there yet - so
            # this stays quiet about it rather than logging a failed lookup
            # every second for thirty seconds.
            spot = self._ad_close_target(ids)
            if spot is not None:
                taps += 1
                step(f"closeAd(): tapping close control at {spot}{self._reaction()}")
                self.device.tap(*spot)
                # Give the SDK a moment to tear the activity down before
                # asking again, so one close is not tapped twice.
                time.sleep(AD_AFTER_TAP)
            else:
                time.sleep(AD_POLL_INTERVAL)

        self._snap("ad-still-open", force=True)
        if required:
            self.failed += 1
            result("closeAd()", False, f"still showing after {timeout}ms")
            raise TestFailure(f"closeAd() could not close the ad within {timeout}ms")
        self.skipped += 1
        skipped("closeAd()", f"still showing after {timeout}ms")
        return False

    def _ad_close_target(self, ids):
        """A point to tap to dismiss the ad, or None if nothing is offered yet.

        Templates first, then text. Text is the fallback rather than the first
        choice because OCR costs about a second and an ad is mostly video: the
        reading is easily a frame or two stale by the time it lands, while a
        template match on the same frame is tens of milliseconds.

        Lookups here are silent - `self._polling` suppresses both the retries
        and the screenshots - because "no close button yet" is the expected
        answer for most of an ad's duration, not a finding worth a log line.
        """
        was_polling, self._polling = self._polling, True
        try:
            frame = self.frame()
            if frame is None:
                return None
            # The two stages are guarded separately and not by one try around
            # both: a project with no ad-close templates at all makes the
            # template stage throw on its first call, and a shared guard would
            # take the text fallback down with it - which is exactly the case
            # the fallback exists for.
            for element_id in ids:
                try:
                    hits = self.matcher.find(frame, element_id, max_results=1)
                except Exception:  # noqa: BLE001 - not in this database, or unreadable
                    continue
                if hits:
                    return hits[0].center
            # One pass for every word rather than a pass per word: `find_any`
            # reads the screen once and honours the order of the list, so this
            # is the same priority at a sixth of the OCR.
            try:
                element = self.text.find_any(frame, list(AD_CLOSE_WORDS), False)
            except Exception:  # noqa: BLE001 - a failed probe just means "not yet"
                return None
            return element.center if element else None
        finally:
            self._polling = was_polling

    # -- assertions ------------------------------------------------------

    def alert(self, expression, name=None):
        """Assert a condition and print the testcase name plus pass/fail status."""
        value = expression() if callable(expression) else expression
        ok = bool(value)
        label = name or _describe(value)
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        result(f"{self.testcase} :: {label}", ok)
        # The frame is the one the lookup behind `expression` decided on, so
        # the picture shows the screen as the assertion saw it - not as it
        # looks now, a second and possibly an animation later.
        boxes = [e.bounds for e in _elements(value)]
        self._snap(label, boxes)
        return ok

    # -- teardown --------------------------------------------------------

    def close(self, error=None):
        if self._closed:
            return
        self._closed = True
        self.screen.stop()
        # An unhandled exception (a failed waitUntil, a missing template, ...)
        # ends auto-play, so the testcase must not be reported as passing.
        if error is None:
            error = _pending_exception()
        if error is not None:
            self.aborted = f"{type(error).__name__}: {error}"
            if self.failed == 0:
                self.failed += 1
            # The last frame is the screen the run died on, which is the one
            # picture an abort leaves nobody else to take.
            step(f"aborted: {self.aborted}")
            self._snap("aborted")
        summary(
            self.testcase, self.passed, self.failed, self.skipped, aborted=self.aborted
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close(error=exc)
        return False


# -- helpers -------------------------------------------------------------


def _multitap_args(target, args, offset, count, duration):
    """Sort out multiTap's two positional forms.

    An element takes an offset before the count; a normalized position has
    nothing to offset, so its count comes first. Which form was used is decided
    by the second argument's own shape: a pair is an offset, a number a count.
    """
    args = list(args)
    if args and offset is None and count is None:
        first = args[0]
        if isinstance(first, (list, tuple)) and len(first) == 2:
            offset = args.pop(0)
        elif first is None:
            args.pop(0)
    if args and count is None:
        count = args.pop(0)
    if args and duration is None:
        duration = args.pop(0)
    if args:
        raise TypeError(f"multiTap() got unexpected extra arguments: {args}")
    count = 2 if count is None else int(count)
    if count < 1:
        raise TestFailure(f"multiTap() needs at least one tap, got {count}")
    duration = None if duration is None else max(0, int(duration))
    return offset, count, duration


def find_database(base_dir):
    """Locate element-database.py near the testcase and load its `db` dict.

    Returns (db, directory) - the relative template paths in `db` are resolved
    against that directory, not against the testcase's own folder.
    """
    seen = []
    for candidate in (base_dir, os.path.dirname(base_dir), os.getcwd()):
        if candidate in seen:
            continue
        seen.append(candidate)
        path = os.path.join(candidate, "element-database.py")
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location("element_database", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            db = getattr(module, "db", None)
            if not isinstance(db, dict):
                raise RuntimeError(f"{path} must define a dict named 'db'")
            return db, candidate
    raise FileNotFoundError(f"element-database.py not found (looked in: {', '.join(seen)})")


def load_database(base_dir):
    return find_database(base_dir)[0]


def _pending_exception():
    """The exception unwinding the script right now, if any (Python 3.12+)."""
    exc = sys.exception() if hasattr(sys, "exception") else None
    if exc is not None:
        return exc
    # atexit runs after unwinding, so fall back to what the script died with.
    last = getattr(sys, "last_exc", None)
    if last is not None and not isinstance(last, SystemExit):
        return last
    return None


def _caller_testcase():
    main = sys.modules.get("__main__")
    path = getattr(main, "__file__", None)
    return os.path.basename(path) if path else "testcase"


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _elements(value):
    """Every Element in an assertion's value, for drawing on its screenshot."""
    if isinstance(value, Element):
        return [value]
    if isinstance(value, (list, tuple)):
        return [v for v in value if isinstance(v, Element)][:8]
    return []


def _as_bounds(element):
    if isinstance(element, Element):
        return element.bounds
    if isinstance(element, (list, tuple)):
        if element and isinstance(element[0], Element):
            return element[0].bounds
        if len(element) == 4:
            return tuple(int(v) for v in element)
    raise TypeError(f"cannot read bounds from {element!r}")


def _clamp(value, low, high):
    return max(low, min(high, int(value)))


def _clamp_bounds(bounds, shape):
    h, w = shape[:2]
    x1, y1, x2, y2 = bounds
    x1 = _clamp(x1, 0, w - 1)
    y1 = _clamp(y1, 0, h - 1)
    x2 = _clamp(x2, x1 + 1, w)
    y2 = _clamp(y2, y1 + 1, h)
    return x1, y1, x2, y2


def _describe(value):
    if isinstance(value, Element):
        return value.label or (f"text {value.text!r}" if value.text else "element")
    if isinstance(value, Position):
        return repr(value)
    if isinstance(value, (list, tuple)):
        if len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
            position = _as_position(value)
            return repr(position) if position else f"({int(value[0])},{int(value[1])})"
        return f"{len(value)} element(s)"
    return repr(value)
