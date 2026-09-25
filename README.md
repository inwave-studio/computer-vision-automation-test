# auto-play

Android UI test SDK. Testcases are plain Python scripts that drive a real
device over ADB: the screen arrives as a live video stream (scrcpy), OpenCV
locates UI elements by image pattern, and OCR reads on-screen text.

## Install

```bash
pip install -r requirements.txt
```

Also needed: `adb` on PATH and a device with USB debugging enabled
(`adb devices` should list it). The scrcpy server is bundled in `vendor/`, so
scrcpy itself does not have to be installed.

## Run a testcase

```bash
python Tests/test_beathopper_onboarding.py       # directly
python -m autoplay Tests/test_beathopper_onboarding.py   # or via the runner
python -m autoplay Tests/*.py -s emulator-5554           # batch, explicit device
```

The runner exits non-zero if any testcase fails, so it drops into CI as-is.

## Element database

`element-database.py` maps an element id to the image that identifies it:

```python
db = {
    "welcome-screen": "DB/welcome-th.png",
    "play-button": "DB/play-button.png",
}
```

Paths are relative to the file itself. Crop templates from a device screenshot;
they are matched across a range of scales, so a template captured on a
differently-sized screen still works.

Crop something with detail in it. A template that is all smooth gradient - a
bare dialog background with the text and buttons left out - has nothing to
correlate against, and scores no better on the screen it came from than on any
other. If an element only fails to match when it is plainly on screen, look at
the template first: `screen-sub.png` is an empty hexagon, and no threshold
makes an empty shape identifiable. Include the wording or the icon.

An element drawn several different ways - the same close button as a bare x on
one popup and a circled x on another - lists every variant instead of one path:

```python
db = {
    "song-card": [
        "DB/songcard-play.png",
        "DB/songcard-ad.png",
    ],
}
```

Nothing else changes: `find("song-card")` searches every listed image and
returns the best match, so adding a variant never touches a testcase.

## Writing a testcase

```python
from autoplay import *

app_id = "com.example.app"
stop(app_id)
clear(app_id)
open_app(app_id)

waitUntil(lambda: find("welcome-screen") or findText("notifications?"), timeout=60_000)
if findText("notifications?"):
    tap(findText("ALLOW"))

alert(findText("Home"), name="home screen is shown")
```

Every method prints what it did, and the run ends with a pass/fail summary. The
log is colourised when the console supports it - method names in bold, matched
screen text in cyan, hits green, misses red, timings dimmed - so a long run can
be skimmed for the line that went wrong. Set `NO_COLOR=1` to turn it off, or
`AUTOPLAY_COLOR=1` to force it on where the check guesses wrong (a CI log
viewer, a pipe).

## API

| Method | Returns | Notes |
| --- | --- | --- |
| `alert(expression, name=None)` | `bool` | Records a pass/fail assertion and prints it |
| `clear(app_id)` | session | Wipes the app's storage (`pm clear`) |
| `open_app(app_id)` | session | Launches the app (also `autoplay.open`) |
| `hide(app_id)` | session | Sends the app to the background (HOME) |
| `kill(app_id)` / `stop(app_id)` | session | Force-stops the app |
| `tap(element)` | `(x, y)` | Accepts an Element, a match list, `(x, y)`, `norm(x, y)`, or a string |
| `doubleTap(element)` | `(x, y)` | Same argument forms as `tap` |
| `multiTap(element, offset, count, duration=None)` | `(x, y)` | Taps the same point `count` times; `duration` in ms spans the whole burst, `offset` shifts it by (dx, dy) pixels |
| `multiTap(target, count, duration=None)` | `(x, y)` | The same without an offset; `target` may be a `norm(x, y)` |
| `readText(element)` | `str` | OCR within the element's bounds |
| `find(element_id, retries=None)` | `list[Element]` | Empty list when absent; `threshold=` is keyword-only |
| `find([id, ...], retries=None)` | `bool` | True if at least one of them is on screen |
| `findLayout(element_id, retries=None)` | `list[Element]` | Like `find` but matches the outline, not the pixels |
| `findText(string, retries=None, case_sensitive=False)` | `Element` or `None` | Matches substrings; ignores case unless asked not to |
| `findText([string, ...], retries=None, case_sensitive=False)` | `Element` or `None` | The first *listed* string that is on screen |
| `isAdShowing(patterns=None)` | `bool` | True if a full-screen ad has focus right now; one adb call, no waiting |
| `waitForAd(timeout=15000, required=False)` | `bool` | Waits for an ad to appear; a no-show is a SKIP, not a failure |
| `closeAd(timeout=90000, required=True)` | `bool` | Waits out the ad, taps its close control, returns when it is gone; `False` if no ad was up |
| `norm(x, y)` | `Position` | A resolution-independent point, `0..1` from the top-left |
| `waitUntil(fn, timeout=10000, required=True)` | the truthy value, or `None` | Fails the testcase and stops on timeout; `required=False` marks an optional step, where a timeout just logs SKIP and returns `None` |
| `wait(ms)` | session | Plain sleep |
| `scrollVerticle(percent)` | session | Negative scrolls the content down (finger swipes up), e.g. `-20` = 20% of height; the swipe is centred on the screen |
| `scrollHorizontal(percent)` | session | Negative scrolls left |

`Element` carries `.center`, `.bounds`, `.text`, `.score`, and is truthy when
found, so it reads naturally in conditions:

```python
skip = findText("Prefer not to say")
if skip:
    tap(skip)
```

### Retries

The second argument to `find`, `findLayout` and `findText` is `retries`, so
`find("promo", 0)` asks once and gives up. Match confidence is `threshold=`,
keyword-only, because passing it by accident is worse than not passing it at
all: too low matches every position on screen, too high can never match.

A lookup that finds nothing retries automatically - 3 more attempts, 100ms
apart - because a screen caught mid-animation is the usual reason a `find` comes
back empty. Pass `retries=` to change it, or `retries=0` to ask exactly once:

```python
find("play-button")               # 1 + 3 attempts
findText("Skip", retries=10)      # for a slow, late-arriving label
find("promo-popup", retries=0)    # a probe that should not wait
```

Inside `waitUntil` the poll loop is already the retry, so lookups there default
to a single attempt rather than multiplying the cost - an OCR pass takes about a
second, so 4 attempts would turn a 2s optional wait into one 4s attempt. An
explicit `retries=` still applies.

### Looking for several things at once

`findText` takes a list, and returns the first string *in the list* that is on
screen - list order decides, not screen position. It costs one OCR pass, not
one per string:

```python
choice = findText(["Continue", "Next", "Tiep tuc"])
```

`find` takes a list too, but answers a different question: whether any of the
elements is present (`bool`), for `waitUntil` conditions.

### Case

`findText` ignores case by default, because OCR is not dependable about it.
When the difference is the whole point - an `OK` button versus the word "ok" in
the sentence next to it - ask for it:

```python
findText("OK", case_sensitive=True)
```

Accents are folded either way. OCR reads Vietnamese diacritics unreliably, so
`findText("Tiep tuc")` matches "Tiếp tục" in both modes; `case_sensitive`
decides only A versus a.

One thing worth knowing when a lookup fails on text you can plainly see: OCR
sometimes misreads a whole word. On the tutorial overlay it returns
`Git va Keo de Dieu khien` for "Giữ và Kéo để Điều khiển" - no amount of folding
recovers `ữ` read as `t`. Match on the part that reads cleanly instead of the
full sentence.

### Normalized positions

`norm(x, y)` is a point given as a fraction of the screen, origin top-left, x
growing right and y growing down - so a testcase written against one device
still taps the right place on another:

```python
tap(norm(0.5, 0.92))               # centre, near the bottom
multiTap(norm(0.5, 0.5), 10, 800)  # 10 taps spread over 800ms
```

A plain `(x, y)` pair is still device pixels; a pair of floats inside `0..1` is
read as normalized.

### Matching by outline

`findLayout` correlates the element's edges instead of its pixels, so it finds a
shape whose colours changed - a themed button, a control over a different
background, a re-skinned dialog - which defeats `find`:

```python
findLayout("close-popup")
```

It keys on shape alone, so it is the looser of the two: prefer `find` when the
artwork is stable, and reach for `findLayout` when it is not.

### Optional steps

Some screens only show up sometimes - a permission prompt, a promo popup, an
A/B-tested survey. Pass `required=False` so a timeout does not fail the run:

```python
prompt = waitUntil(
    lambda: findText("notifications?"),
    timeout=8_000,
    label="allow notifications prompt",
    required=False,
)
if prompt:
    tap(findText("ALLOW"))
```

Skipped steps are printed as `SKIP` and counted in the final summary, so an
optional step that silently stopped appearing is still visible.

### Interstitial and rewarded ads

```python
tap(find("watch-ad-button"))
if waitForAd():          # optional by default - fill rate is never 100%
    closeAd()            # waits out the countdown, taps close, returns when gone
alert(find("reward-granted"))
```

`isAdShowing()` answers the same question without waiting, which is what you
want in a `waitUntil` condition that has to tolerate an ad appearing on top:

```python
waitUntil(lambda: find("home-screen") or isAdShowing())
```

The two halves work differently on purpose. **Whether** an ad is up is read
from the window, not the screen: the ad SDK is a library inside the app's own
process, so the package name tells you nothing, but the focused *activity
class* names the network exactly - `ControllerActivity` is IronSource,
`AppLovinInterstitialActivity` is AppLovin. No threshold, no template, one
`dumpsys` call of about 150ms.

**How** to dismiss it is a vision problem and is left to the normal lookup
stack, because a close button appears only after a countdown, sits in a
different corner per network, and is drawn as an x, a circled x, or the word
Skip. `closeAd` polls the window until the ad is gone, and on each pass looks
for a way out: first the element-database entries `ad-close`, `ad-skip` and
`close-popup`, then the words *Skip Ad*, *Skip*, *Close*, *Continue*, *Đóng*
and *Bỏ qua*. Missing database entries are skipped rather than raising, so a
project with no ad templates still runs on the text alone - add a template
when a network's button carries no readable word.

The back key is deliberately never pressed. Most SDKs swallow it until the
reward is earned, and the ones that do not record "user abandoned the ad",
which is a different event from closing one and skews exactly the metrics an
ad testcase exists to measure.

Defaults reflect how ads actually behave: `waitForAd` gives up after 15s
because an ad that has not started by then is not coming, while `closeAd`
allows 90s because a rewarded video commonly runs 30s and is only closable at
the end. A network that is not in the built-in list can be named per call:

```python
closeAd(patterns=("com.newnetwork.",))
```

## Running a folder of testcases

`test-runner.py` runs every testcase in a folder, prints a table, and writes a
self-contained HTML report:

```
python test-runner.py Tests
python test-runner.py Tests -s <adb-serial> -r report.html
python test-runner.py Tests -q                 # verdicts only, no per-step log
python test-runner.py Tests --color never      # or always, for a CI log viewer
```

Each testcase's own log is echoed live, indented under its heading, so a run
that takes minutes on a device can be followed as it happens:

```
[1/2] Tests/test_playtut.py
    [ 29.71s] findText('POP'): found 'POP' at (306, 384)
    [ 29.71s] tap(text 'POP'): tapping (608,768)  [659ms since frame]
      PASS  tutorial song screen is shown
    -> PASSED  (58.7s)
```

```
TESTCASE               STATUS  ASSERTS  SKIP  TIME   DETAIL
---------------------  ------  -------  ----  -----  ------
test_api_behaviour.py  PASSED  49/49    -     16.3s
test_playtut.py        FAILED  7/9      1     42.1s  2 failed

1/2 testcases passed, 1 failed
```

Each testcase runs in its own subprocess, so one crashing or hanging run cannot
take the others down - a hang is reported as `TIMEOUT` (`-t` sets the limit, 600s
by default) and an unhandled exception as `ERROR`, with its console output kept
in the report. The exit code is non-zero if anything failed, for CI.

### What the report shows

Every testcase expands into its own timeline - each step, each `alert`, each
skipped optional step, at the second it happened - and the steps that looked at
the screen carry the picture they decided on:

- **screen** - the frame the step ran against, with a green box round what it
  matched. Not a fresh screenshot: re-grabbing at report time would show a
  screen that has since moved on, which is the one thing a failure screenshot
  must not do.
- **detected element** - a close-up of the match, cropped with a margin so it
  can still be placed on the screen it came from.
- **looking for** - on a `find` that missed, the template image from the
  element database, beside the screen it was not found on. The two side by side
  usually answer it outright: same artwork on a different background means the
  template is too tight, nothing like it on screen means the app went somewhere
  else.

A testcase that aborts gets a final shot of the screen it died on. Failed
testcases open expanded; passed ones are collapsed.

Pictures are only taken when a report is being written, so `--no-report` and a
testcase run by hand cost nothing. They go in a folder named after the report
(`report.html` -> `report_files/`), which is cleared at the start of each run -
keep a run by copying both, or by pointing `-r` somewhere else.

## How it works

- `autoplay/device.py` - ADB: app lifecycle, touch injection, screen geometry.
- `autoplay/screen.py` - pushes the bundled scrcpy server, reads its H.264
  stream on a background thread, and keeps the newest frame. Falls back to
  `adb exec-out screencap` if the stream cannot start.
- `autoplay/vision.py` - multi-scale template and outline matching with
  non-maximum suppression, plus OCR (RapidOCR/ONNX, no native install needed).
- `autoplay/session.py` - the testcase API and the pass/fail bookkeeping.
- `autoplay/report.py` - screenshots and the step timeline, when a report is
  being written. Idle otherwise.
- `test-runner.py` - runs a folder of testcases and writes the HTML report.

Two details worth knowing when templates behave oddly:

- **Scale.** A template is searched across a range of scales - coarsely first
  to locate the peak, then finely around the winner - and the winning scale is
  cached per element, so the first `find()` costs a second or two and later
  ones tens of milliseconds. The floor follows the frame, so a template still
  matches on a downscaled stream rather than bottoming out at a fixed limit.
- **Border background.** A template cropped from a screenshot carries a rim of
  the background behind it, which drags the score down over different artwork.
  Each template is therefore also matched border-trimmed, and the better
  variant wins.
- **Outline matching.** `findLayout` scores how well a template's Canny edges
  sit on the frame's, in both directions: how much of the template's outline
  landed on a screen edge, and how much of the screen's edging in that window
  the template accounts for. One without the other matches anything busy, or
  anything at all. It scores against a distance field rather than the raw edge
  map, because a one-pixel-wide stroke resampled to a slightly different scale
  lands a pixel off and a direct comparison collapses - a crop scored 0.62
  against the very frame it came from. Templates are also kept from shrinking
  much below their natural size: a wide banner squeezed to a sliver keeps just a
  few strokes, and a few strokes fit almost anywhere.

### Stream size and latency

The screen is streamed at a reduced resolution (`max_size=1200` on the longest
edge) rather than the device's own. Template matching cost scales with frame
area and dominates every step, so at native resolution a single `find()` can
take longer than the timeout the caller is waiting inside - the poll loop then
gets one attempt and gives up on a screen that was really there.

The floor is OCR, which fails at a cliff: it reads a permission prompt at 1100
and loses it at 1050. 1200 keeps headroom over that while matching ~3x faster
than native. Pass `Screen(device, max_size=...)` to override, or `0` to stream
the device's own resolution.

Every input logs how long it has been since the frame it is reacting to was
grabbed:

```
tap(text 'POP'): tapping (189,1518)  [764ms since frame]
```

That span is what decides whether a tap can still land on what the frame
showed, so it is the number to watch when taps start missing a moving target.
Frame age within the stream (~280ms glass-to-frame on the measured device) is
on top of it. `bench/README.md` has the full measurements and the scripts that
produced them.
