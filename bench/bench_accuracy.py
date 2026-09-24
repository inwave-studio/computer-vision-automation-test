"""Which stream size is still accurate enough? (design.md task 3, bullet 1)

Speed is only half of "kich thuoc toi uu" - a smaller stream that stops finding
things is not an optimisation. Streams the app's tutorial screen at each size
and checks both OCR needles and template matching against known-good answers.
"""

import statistics
import sys
import time

from autoplay.device import Device
from autoplay.screen import Screen
from autoplay.session import find_database
from autoplay.vision import TemplateMatcher, TextFinder

# What the tutorial song screen must yield, whatever the stream size.
NEEDLES = ["bài hát đầu tiên", "Believer", "Imagine Dragons", "Justin Bieber"]
TEMPLATE = "play-button"
EXPECTED_BUTTONS = 4
# Read at native size first: if this is missing, the app is not on the screen
# the expectations describe and the row would be meaningless.
GUARD = "bài hát đầu tiên"


def run(size, rounds=3):
    device = Device()
    screen = Screen(device, max_size=size)
    screen.start()
    if not screen._streaming:
        print(f"max_size={size}: stream failed")
        screen.stop()
        return None

    db, db_dir = find_database(".")
    text = TextFinder()
    frame = screen.latest()
    text.read_all(frame)  # warm

    h, w = frame.shape[:2]
    # Guard against the app navigating away mid-sweep: a size that looks bad
    # only because the screen changed would be a false conclusion.
    if text.find(frame, GUARD) is None:
        screen.stop()
        print(f"max_size={size}: SKIPPED - not on the expected screen")
        return None
    found = {}
    ocr_ms = []
    for needle in NEEDLES:
        f = screen.latest()
        t = time.time()
        el = text.find(f, needle)
        ocr_ms.append((time.time() - t) * 1000.0)
        found[needle] = el is not None

    matcher = TemplateMatcher(db, base_dir=db_dir)
    f = screen.latest()
    t = time.time()
    hits = matcher.find(f, TEMPLATE)
    first_ms = (time.time() - t) * 1000.0
    cached_ms = []
    counts = [len(hits)]
    for _ in range(rounds):
        f = screen.latest()
        t = time.time()
        counts.append(len(matcher.find(f, TEMPLATE)))
        cached_ms.append((time.time() - t) * 1000.0)

    screen.stop()
    return {
        "size": size,
        "wh": (w, h),
        "ocr_ok": sum(found.values()),
        "ocr_total": len(NEEDLES),
        "ocr_ms": statistics.median(ocr_ms),
        "buttons": statistics.median(counts),
        "first_ms": first_ms,
        "cached_ms": statistics.median(cached_ms),
        "detail": found,
    }


if __name__ == "__main__":
    sizes = [int(a) for a in sys.argv[1:]] or [0, 1080, 800, 640]
    rows = [r for r in (run(s) for s in sizes) if r]
    print("\n== accuracy vs size ==")
    print(f"{'max_size':>9}{'frame':>12}{'ocr':>8}{'ocr ms':>9}{'buttons':>9}{'match1':>9}{'matchN':>9}")
    for r in rows:
        print(
            f"{r['size']:>9}{r['wh'][0]}x{r['wh'][1]:<7}"
            f"{r['ocr_ok']}/{r['ocr_total']:<5}{r['ocr_ms']:>8.0f}"
            f"{r['buttons']:>9.0f}{r['first_ms']:>9.0f}{r['cached_ms']:>9.0f}"
            + ("" if r["buttons"] == EXPECTED_BUTTONS else "   <-- WRONG COUNT")
        )
        for k, v in r["detail"].items():
            if not v:
                print("            missed text: " + k.encode("ascii","replace").decode())
