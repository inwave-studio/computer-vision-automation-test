"""Device-free checks for the API rules added in design.md tasks 4, 5, 7 and 8.

These exercise the decision logic - retrying, multi-string lookup, database
variants, normalized positions, multiTap's argument forms - against fake
screens and a recording stand-in for the device, so they run without a phone
attached and without the scrcpy stream.

    python Tests/test_api_behaviour.py
"""

import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoplay.session import (  # noqa: E402
    DEFAULT_RETRIES,
    Position,
    Session,
    TestFailure,
    _multitap_args,
    norm,
)
from autoplay.vision import (  # noqa: E402
    MODE_EDGE,
    Element,
    TemplateMatcher,
    template_paths,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}{' - ' + detail if detail else ''}")


# -- stand-ins -----------------------------------------------------------


class FakeDevice:
    """Records what would have been sent to adb."""

    def __init__(self, width=1080, height=2400):
        self.width, self.height = width, height
        self.serial = "fake"
        self.taps = []
        self.multi = []

    def tap(self, x, y):
        self.taps.append((x, y))

    def double_tap(self, x, y, gap=0.08):
        self.taps += [(x, y), (x, y)]

    def multi_tap(self, x, y, count, interval=0.0):
        self.multi.append((x, y, count, interval))
        self.taps += [(x, y)] * count
        return count * 10.0


class FakeScreen:
    """Hands out a scripted sequence of frames."""

    def __init__(self, frames, width=1080, height=2400):
        self.frames = list(frames)
        self.grabs = 0
        self._w, self._h = width, height

    def latest(self, max_age=0.0):
        frame = self.frames[min(self.grabs, len(self.frames) - 1)]
        self.grabs += 1
        return frame

    def to_device(self, x, y):
        return int(x), int(y)

    def stop(self):
        pass


class FakeText:
    """OCR stand-in: each call returns the next scripted screen of texts."""

    def __init__(self, screens):
        self.screens = list(screens)
        self.calls = 0

    def _texts(self):
        screen = self.screens[min(self.calls, len(self.screens) - 1)]
        self.calls += 1
        return [
            Element(10 + 40 * i, 20 * i, 30, 12, score=0.9, text=t)
            for i, t in enumerate(screen)
        ]

    def read_all(self, screen):
        return self._texts()

    def find_any(self, screen, needles, case_sensitive=False):
        from autoplay.vision import TextFinder

        texts = self._texts()
        for needle in needles:
            element = TextFinder()._pick(texts, needle, case_sensitive)
            if element:
                return element
        return None


def make_session(frames=None, texts=None, matcher=None):
    """A Session with every device-touching part replaced."""
    session = Session.__new__(Session)
    session.testcase = "fake"
    session.device = FakeDevice()
    session.screen = FakeScreen(frames or [np.zeros((100, 100, 3), np.uint8)])
    session.text = FakeText(texts or [[]])
    session.matcher = matcher
    session.passed = session.failed = session.skipped = 0
    session.aborted = None
    session._frame_at = None
    session._last_frame = None
    session._polling = False
    session._closed = True  # never let atexit/close run against fakes
    return session


# -- task 4: automatic retries -------------------------------------------

print("\ntask 4 - retry on a miss")

s = make_session(texts=[[], [], ["Continue"]])
found = s.findText("Continue")
check("findText retries until the text appears", bool(found), f"got {found!r}")
check("it took 3 OCR passes", s.text.calls == 3, f"{s.text.calls} calls")

s = make_session(texts=[[]])
missing = s.findText("nope")
check("a real miss gives up and returns None", missing is None)
check(
    f"a miss costs 1+{DEFAULT_RETRIES} attempts",
    s.text.calls == DEFAULT_RETRIES + 1,
    f"{s.text.calls} calls",
)

s = make_session(texts=[[]])
s.findText("nope", retries=0)
check("retries=0 tries exactly once", s.text.calls == 1, f"{s.text.calls} calls")

s = make_session(texts=[[]])
s.findText("nope", retries=1)
check("retries=1 tries twice", s.text.calls == 2, f"{s.text.calls} calls")

# Inside waitUntil the poll loop is already the retry, so a lookup must not
# multiply attempts - otherwise one 2s optional wait becomes one 4s attempt.
s = make_session(texts=[[]])
s._polling = True
s.findText("nope")
check("no extra retries while waitUntil polls", s.text.calls == 1, f"{s.text.calls} calls")

s = make_session(texts=[[]])
s._polling = True
s.findText("nope", retries=2)
check("an explicit retries= still applies while polling", s.text.calls == 3, f"{s.text.calls} calls")


class CountingMatcher:
    """Finds `element_id` only from the nth call onwards."""

    def __init__(self, hit_on=1, element_id="thing"):
        self.hit_on, self.element_id, self.calls = hit_on, element_id, 0

    def variant_count(self, element_id):
        return 1

    def find(self, screen, element_id, threshold=None, max_results=0, mode=None):
        self.calls += 1
        if self.calls >= self.hit_on:
            return [Element(5, 5, 10, 10, score=0.9, label=element_id)]
        return []


m = CountingMatcher(hit_on=3)
s = make_session(matcher=m)
check("find() retries until the element appears", bool(s.find("thing")), "")
check("it took 3 match attempts", m.calls == 3, f"{m.calls} calls")

m = CountingMatcher(hit_on=99)
s = make_session(matcher=m)
check("find() gives up and returns []", s.find("thing") == [])
check(f"after 1+{DEFAULT_RETRIES} attempts", m.calls == DEFAULT_RETRIES + 1, f"{m.calls}")

m = CountingMatcher(hit_on=99)
s = make_session(matcher=m)
s.find(["a", "b"])
check(
    "find([...]) retries the whole list, not each id",
    m.calls == (DEFAULT_RETRIES + 1) * 2,
    f"{m.calls} calls",
)


# -- task 5: findText over a list ----------------------------------------

print("\ntask 5 - findText(list of strings)")

s = make_session(texts=[["Cancel", "Continue", "Skip"]])
el = s.findText(["Continue", "Skip"])
check("returns an element for a listed text", bool(el))
check("one OCR pass serves the whole list", s.text.calls == 1, f"{s.text.calls} calls")

# "first in the array", not "first on screen": Skip is listed first, so Skip
# wins even though Continue sits above it.
s = make_session(texts=[["Continue", "Skip"]])
el = s.findText(["Skip", "Continue"])
check("array order decides, not screen order", el.text == "Skip", f"got {el.text!r}")

s = make_session(texts=[["Continue"]])
el = s.findText(["Missing", "Continue"])
check("falls through to a later entry", el.text == "Continue", f"got {el.text!r}")

s = make_session(texts=[[]])
check("none present -> None", s.findText(["a", "b"]) is None)
check(
    "a miss on a list still retries",
    s.text.calls == DEFAULT_RETRIES + 1,
    f"{s.text.calls} calls",
)

s = make_session(texts=[["Tiếp tục"]])
el = s.findText(["Continue", "Tiep tuc"])
check("accents still folded inside a list", bool(el), "")


# -- findText: case sensitivity ------------------------------------------

print("\nfindText(case_sensitive=)")

s = make_session(texts=[["Continue"]])
check("insensitive by default", bool(s.findText("continue")))

s = make_session(texts=[["Continue"]])
check(
    "case_sensitive=True rejects the wrong case",
    s.findText("continue", case_sensitive=True, retries=0) is None,
)

s = make_session(texts=[["Continue"]])
check(
    "case_sensitive=True accepts the right case",
    bool(s.findText("Continue", case_sensitive=True)),
)

# The two halves are independent: exact case must not re-introduce the accent
# strictness that OCR cannot deliver.
s = make_session(texts=[["Tiếp tục"]])
check(
    "accents stay folded when case-sensitive",
    bool(s.findText("Tiep tuc", case_sensitive=True)),
)

s = make_session(texts=[["Tiếp tục"]])
check(
    "case still checked under folded accents",
    s.findText("tiep tuc", case_sensitive=True, retries=0) is None,
)

# Substrings, not just whole strings.
s = make_session(texts=[["Press OK to continue"]])
check(
    "case-sensitive substring hits",
    bool(s.findText("OK", case_sensitive=True)),
)

s = make_session(texts=[["Press ok to continue"]])
check(
    "case-sensitive substring misses the wrong case",
    s.findText("OK", case_sensitive=True, retries=0) is None,
)

# A list lookup passes the flag through to every entry.
s = make_session(texts=[["SKIP"]])
check(
    "case_sensitive applies across a list",
    s.findText(["Skip", "skip"], case_sensitive=True, retries=0) is None,
)

s = make_session(texts=[["SKIP"]])
check(
    "the correctly-cased entry in a list still wins",
    bool(s.findText(["Skip", "SKIP"], case_sensitive=True)),
)

s = make_session(texts=[["Đồng ý"]])
check(
    "'d' with stroke folds in both cases",
    bool(s.findText("Dong y", case_sensitive=True)),
)


# -- task 7: element variants --------------------------------------------

print("\ntask 7 - one element, several images")

check("a plain path is one variant", template_paths("a.png") == ["a.png"])
check("a list is several", template_paths(["a.png", "b.png"]) == ["a.png", "b.png"])
check(
    "a dict form works too",
    template_paths({"variants": ["a.png", "b.png"]}) == ["a.png", "b.png"],
)

matcher = TemplateMatcher(
    {
        "one": "DB/play-button.png",
        "two": ["DB/songcard-play.png", "DB/songcard-ad.png"],
    },
    base_dir=ROOT,
)
check("variant_count reads the database", matcher.variant_count("two") == 2)
check("a single-path element counts 1", matcher.variant_count("one") == 1)
check(
    "each variant also gets a border-trimmed copy",
    len(matcher._variants("two")) == 4,
    f"{len(matcher._variants('two'))}",
)

# The second listed image is on screen; the first is not. A single-image
# element could not match this, so finding it proves every variant is searched.
second = cv2.imread(os.path.join(ROOT, "DB/songcard-ad.png"), cv2.IMREAD_UNCHANGED)[:, :, :3]
screen = np.full((1200, 540, 3), 30, np.uint8)
screen[300 : 300 + second.shape[0], 40 : 40 + second.shape[1]] = second
hits = matcher.find(screen, "two", max_results=1)
check("find() matches a non-first variant", bool(hits), "no match")

# A real element database has to keep working.
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("edb", os.path.join(ROOT, "element-database.py"))
edb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edb)
real = TemplateMatcher(edb.db, base_dir=ROOT)
broken = []
for element_id in edb.db:
    try:
        real._images(element_id)
    except Exception as exc:  # noqa: BLE001
        broken.append(f"{element_id}: {exc}")
check("every image in element-database.py loads", not broken, "; ".join(broken))


# -- task 8: findLayout, normalized positions, multiTap -------------------

print("\ntask 8 - new API methods")

# findLayout keys on shape, so it still finds an element whose colours were
# inverted - which defeats pixel template matching.
plain = cv2.imread(os.path.join(ROOT, "DB/close-popup.png"), cv2.IMREAD_UNCHANGED)[:, :, :3]
canvas = np.full((900, 700, 3), 20, np.uint8)
cv2.rectangle(canvas, (60, 60), (640, 380), (70, 70, 90), -1)
inverted = cv2.bitwise_not(plain)
canvas[500 : 500 + plain.shape[0], 200 : 200 + plain.shape[1]] = inverted

layout_db = TemplateMatcher({"x": "DB/close-popup.png"}, base_dir=ROOT)
by_pixels = layout_db.find(canvas, "x", max_results=1)
by_outline = TemplateMatcher({"x": "DB/close-popup.png"}, base_dir=ROOT).find(
    canvas, "x", max_results=1, mode=MODE_EDGE
)
check("template matching misses the recoloured element", not by_pixels)
check("findLayout finds it by outline", bool(by_outline), "edge match failed too")

# ...and it must not fire on a screen that does not hold the element at all.
empty = np.full((900, 700, 3), 20, np.uint8)
cv2.rectangle(empty, (60, 60), (640, 380), (70, 70, 90), -1)
cv2.putText(empty, "Nothing here", (90, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (240, 240, 240), 3)
spurious = TemplateMatcher({"x": "DB/close-popup.png"}, base_dir=ROOT).find(
    empty, "x", max_results=1, mode=MODE_EDGE
)
check("findLayout stays quiet on an unrelated screen", not spurious, f"{spurious}")

# Normalized positions: top-left origin, x right, y down.
check("norm(0,0) is the top-left", Position(0, 0).to_device(1080, 2400) == (0, 0))
check("norm(1,1) is the bottom-right", Position(1, 1).to_device(1080, 2400) == (1079, 2399))
check("y grows downwards", Position(0.5, 0.25).to_device(1080, 2400) == (540, 600))
check("norm((x, y)) works", norm((0.5, 0.5)).to_device(1080, 2400) == (540, 1200))

s = make_session()
s.tap(norm(0.5, 0.25))
check("tap(norm) lands on the right pixel", s.device.taps == [(540, 600)], f"{s.device.taps}")

s = make_session()
s.doubleTap(norm(0.25, 0.75))
check("doubleTap(norm) taps twice", s.device.taps == [(270, 1800)] * 2, f"{s.device.taps}")

# A float pair inside 0..1 is normalized; an int pair stays pixels.
s = make_session()
s.tap((0.5, 0.5))
check("a float pair is read as normalized", s.device.taps == [(540, 1200)], f"{s.device.taps}")
s = make_session()
s.tap((540, 1200))
check("an int pair is still pixels", s.device.taps == [(540, 1200)], f"{s.device.taps}")

# multiTap's two positional forms.
check(
    "multiTap(element, offset, count, duration)",
    _multitap_args("el", ((10, -5), 3, 200), None, None, None) == ((10, -5), 3, 200),
)
check(
    "multiTap(norm, count, duration)",
    _multitap_args(norm(0.5, 0.5), (3, 200), None, None, None) == (None, 3, 200),
)
check("keywords work too", _multitap_args("el", (), (1, 2), 5, 300) == ((1, 2), 5, 300))

s = make_session()
s.multiTap(norm(0.5, 0.5), 5, 200)
check("multiTap issues the requested taps", s.device.multi[0][2] == 5, f"{s.device.multi}")
check(
    "count-1 gaps span the duration",
    abs(s.device.multi[0][3] - 0.05) < 1e-9,
    f"interval {s.device.multi[0][3]}",
)

s = make_session()
s.multiTap(Element(100, 200, 40, 40, label="btn"), (10, -5), 3)
check(
    "an offset shifts the point (+y is down)",
    s.device.multi[0][:2] == (130, 215),
    f"{s.device.multi[0][:2]}",
)

s = make_session()
s.multiTap(norm(0.5, 0.5), 4)
check("no duration means no interval", s.device.multi[0][3] == 0.0, f"{s.device.multi}")

# The offset must not push a tap off the screen.
s = make_session()
s.multiTap(norm(1.0, 1.0), (500, 500), 1)
x, y = s.device.multi[0][:2]
check("an offset is clamped to the screen", (x, y) == (1079, 2399), f"({x},{y})")

try:
    _multitap_args("el", (), None, 0, None)
    ok = False
except TestFailure:
    ok = True
check("a count below 1 is rejected", ok)

try:
    _multitap_args("el", (1, 2, 3), None, None, None)
    ok = False
except TypeError:
    ok = True
check("extra positional arguments are rejected", ok)


# -- ads: detecting and closing a full-screen ad -------------------------

print("\nads - detect by window, close by vision")

from autoplay.ads import activity_class, looks_like_ad

GAME = "com.amanotes.beathopper/com.amanotes.beathopper.IWUnityPlayerActivity"
IRONSRC = "com.amanotes.beathopper/com.ironsource.sdk.controller.ControllerActivity"

check("an ad activity is recognised", looks_like_ad(IRONSRC))
check("the app's own activity is not", not looks_like_ad(GAME))
check("an empty focus is not an ad", not looks_like_ad(""))
check(
    "a class merely containing 'ad' is not an ad",
    not looks_like_ad("com.pkg/com.pkg.LoadingActivity")
    and not looks_like_ad("com.pkg/com.pkg.DownloadThreadActivity"),
)
check("the class name is shortened for the log", activity_class(IRONSRC) == "ControllerActivity")
check(
    "every mediation SDK in the list is matched",
    all(
        looks_like_ad(a)
        for a in (
            "p/com.google.android.gms.ads.AdActivity",
            "p/com.applovin.adview.AppLovinInterstitialActivity",
            "p/com.unity3d.ads.adunit.AdUnitActivity",
            "p/com.vungle.ads.internal.ui.VungleActivity",
            "p/com.mbridge.msdk.reward.player.MBRewardVideoActivity",
            "p/com.bytedance.sdk.openadsdk.activity.TTFullScreenVideoActivity",
        )
    ),
)


class ScriptedFocus(FakeDevice):
    """A device whose focused activity follows a script, one entry per call."""

    def __init__(self, activities):
        super().__init__()
        self.activities = list(activities)
        self.polls = 0

    def focused_activity(self):
        current = self.activities[min(self.polls, len(self.activities) - 1)]
        self.polls += 1
        return current


def ad_session(activities, matcher=None, texts=None):
    session = make_session(texts=texts, matcher=matcher)
    session.device = ScriptedFocus(activities)
    return session


s = ad_session([IRONSRC])
check("isAdShowing() is True while an ad has focus", s.isAdShowing() is True)

s = ad_session([GAME])
check("isAdShowing() is False in the app", s.isAdShowing() is False)

# An adb call that fails must read as "no ad", never as an exception: ad
# detection is not allowed to be the thing that fails a testcase.
class BrokenFocus(FakeDevice):
    def focused_activity(self):
        return ""


s = make_session()
s.device = BrokenFocus()
check("an unreadable focus reads as no ad", s.isAdShowing() is False)


class AdCloseMatcher:
    """No close button until `ready_on`, then one in a fixed spot."""

    def __init__(self, ready_on=2, element_id="ad-close"):
        self.calls = 0
        self.ready_on = ready_on
        self.element_id = element_id

    def find(self, screen, element_id, threshold=None, max_results=0, mode=None):
        if element_id != self.element_id:
            raise KeyError(element_id)  # not in this project's database
        self.calls += 1
        if self.calls >= self.ready_on:
            return [Element(900, 100, 60, 60, score=0.95, label=element_id)]
        return []


# The ad stays up for two polls, then the close button appears and it goes.
matcher = AdCloseMatcher(ready_on=2)
s = ad_session([IRONSRC, IRONSRC, IRONSRC, GAME], matcher=matcher)
s.frame = lambda fresh=False: np.zeros((100, 100, 3), np.uint8)
closed = s.closeAd(timeout=5_000)
check("closeAd() returns True once the ad is gone", closed is True)
check("it tapped the close control", len(s.device.taps) == 1, f"{s.device.taps}")
check(
    "the tap landed on the button's centre",
    s.device.taps == [(930, 130)],
    f"{s.device.taps}",
)

s = ad_session([GAME])
check("closeAd() with no ad up returns False", s.closeAd() is False)
check("and taps nothing", not s.device.taps)

# An ad that never closes is a real failure when required.
s = ad_session([IRONSRC])
s.frame = lambda fresh=False: None  # nothing to look at, no close found
try:
    s.closeAd(timeout=600)
    ok = False
except TestFailure:
    ok = True
check("an ad that never closes fails the testcase", ok)
check("and is counted as a failure", s.failed == 1, f"failed={s.failed}")

s = ad_session([IRONSRC])
s.frame = lambda fresh=False: None
check("required=False turns that into a skip", s.closeAd(timeout=600, required=False) is False)
check("counted as skipped", s.skipped == 1, f"skipped={s.skipped}")

# waitForAd is optional by default: no ad is normal, not a broken testcase.
s = ad_session([GAME])
check("waitForAd() returns False when none shows", s.waitForAd(timeout=600) is False)
check("and records a skip, not a failure", s.skipped == 1 and s.failed == 0)

s = ad_session([GAME, IRONSRC])
check("waitForAd() returns True when one appears", s.waitForAd(timeout=5_000) is True)

s = ad_session([GAME])
try:
    s.waitForAd(timeout=600, required=True)
    ok = False
except TestFailure:
    ok = True
check("required=True makes a missing ad a failure", ok)

# A network the built-in list does not know can be named by the testcase.
CUSTOM = "com.pkg/com.newnetwork.ShowAdActivity"
s = ad_session([CUSTOM])
check("an unknown ad activity is not matched by default", s.isAdShowing() is False)
s = ad_session([CUSTOM])
check(
    "patterns= lets a testcase add its own",
    s.isAdShowing(patterns=("com.newnetwork.",)) is True,
)

# The close-button text fallback, for an ad with no template in the database.
s = ad_session([IRONSRC, IRONSRC, GAME], matcher=None, texts=[["Skip Ad"]])
s.frame = lambda fresh=False: np.zeros((100, 100, 3), np.uint8)
check("closeAd() falls back to reading the close text", s.closeAd(timeout=5_000) is True)
check("it tapped what OCR found", len(s.device.taps) == 1, f"{s.device.taps}")


# A blank focus read mid-ad is "cannot tell", not "the ad closed": on a real
# device every activity change is preceded by a poll where nothing holds focus.
s = ad_session([IRONSRC, "", IRONSRC, "", GAME], matcher=None, texts=[[]])
s.frame = lambda fresh=False: None
check("a blank focus does not count as closed", s.closeAd(timeout=5_000) is True)
check("it waited for a named window", s.device.polls >= 5, f"{s.device.polls} polls")


# A template lookup that blows up must not take the text fallback with it:
# a project with no ad-close entries at all raises on the very first id, and
# that is precisely the project the text fallback exists to serve.
class ExplodingMatcher:
    def find(self, screen, element_id, threshold=None, max_results=0, mode=None):
        raise RuntimeError("database not loaded")


s = ad_session([IRONSRC, IRONSRC, GAME], matcher=ExplodingMatcher(), texts=[["Close"]])
s.frame = lambda fresh=False: np.zeros((100, 100, 3), np.uint8)
check("a broken template lookup still reaches the text fallback", s.closeAd(timeout=5_000) is True)
check("and tapped the text it read", len(s.device.taps) == 1, f"{s.device.taps}")

# One OCR pass per poll, not one per candidate word.
s = ad_session([IRONSRC, IRONSRC, GAME], matcher=None, texts=[[]])
s.frame = lambda fresh=False: np.zeros((100, 100, 3), np.uint8)
s.closeAd(timeout=1_200, required=False)
check("a poll that finds nothing costs one OCR pass", s.text.calls <= 2, f"{s.text.calls} passes")


print(f"\nTESTCASE test_api_behaviour.py: {'PASSED' if not failed else 'FAILED'}  "
      f"({passed}/{passed + failed} assertions passed)")
sys.exit(1 if failed else 0)
