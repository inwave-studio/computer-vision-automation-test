"""Latency benchmark for the auto-play screen pipeline (design.md task 3).

Measures, per configuration:
  * startup      - time to first decoded frame
  * grab         - cost of screen.latest()
  * stream lag   - device change -> visible in the stream (glass-to-frame)
  * ocr / match  - cost of the work done on each frame
"""

import statistics
import sys
import time

import numpy as np

from autoplay.device import Device
from autoplay.screen import Screen
from autoplay.vision import TemplateMatcher, TextFinder
from autoplay.session import find_database


def _p(label, values, unit="ms"):
    if not values:
        print(f"    {label:<14} n/a")
        return
    med = statistics.median(values)
    print(
        f"    {label:<14} median {med:7.1f}{unit}  "
        f"min {min(values):7.1f}  max {max(values):7.1f}  n={len(values)}"
    )


def measure_stream_lag(device, screen, rounds=5):
    """Time from a device-side visual change to that change reaching the stream.

    The notification shade is a large, instant, repeatable change, so it makes
    a clean trigger: collapse it, settle, then expand and watch the frames.
    """
    lags = []
    for _ in range(rounds):
        device.shell("cmd statusbar collapse")
        time.sleep(1.2)
        before = screen.latest()
        t0 = time.time()
        device.shell("cmd statusbar expand")
        deadline = t0 + 3.0
        while time.time() < deadline:
            frame = screen.latest()
            if frame.shape == before.shape:
                diff = float(np.mean(cv2_absdiff(frame, before)))
                if diff > 12.0:
                    lags.append((time.time() - t0) * 1000.0)
                    break
        device.shell("cmd statusbar collapse")
        time.sleep(0.6)
    return lags


def cv2_absdiff(a, b):
    import cv2

    return cv2.absdiff(a, b)


def run(label, screen_kwargs, rounds=12):
    print(f"\n=== {label} ===")
    device = Device()
    screen = Screen(device, **screen_kwargs)

    t0 = time.time()
    screen.start()
    startup = (time.time() - t0) * 1000.0
    if not screen._streaming:
        print("    stream failed to start")
        screen.stop()
        return None

    frame = screen.latest()
    h, w = frame.shape[:2]
    print(f"    frame          {w}x{h}   startup {startup:.0f}ms")

    grabs = []
    for _ in range(rounds * 3):
        t = time.time()
        screen.latest()
        grabs.append((time.time() - t) * 1000.0)
        time.sleep(0.02)
    _p("grab", grabs)

    lags = measure_stream_lag(device, screen)
    _p("stream lag", lags)

    db, db_dir = find_database(".")
    matcher = TemplateMatcher(db, base_dir=db_dir)
    text = TextFinder()

    frame = screen.latest()
    text.read_all(frame)  # warm the OCR engine

    ocr = []
    for _ in range(5):
        f = screen.latest()
        t = time.time()
        text.read_all(f)
        ocr.append((time.time() - t) * 1000.0)
    _p("ocr", ocr)

    first = []
    cached = []
    for element in ("play-button",):
        m = TemplateMatcher(db, base_dir=db_dir)
        f = screen.latest()
        t = time.time()
        m.find(f, element)
        first.append((time.time() - t) * 1000.0)
        for _ in range(4):
            f = screen.latest()
            t = time.time()
            m.find(f, element)
            cached.append((time.time() - t) * 1000.0)
    _p("match(1st)", first)
    _p("match(cached)", cached)

    screen.stop()
    return {
        "label": label,
        "size": (w, h),
        "startup": startup,
        "grab": statistics.median(grabs),
        "lag": statistics.median(lags) if lags else None,
        "ocr": statistics.median(ocr),
        "match_first": statistics.median(first),
        "match_cached": statistics.median(cached),
    }


if __name__ == "__main__":
    configs = []
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"

    if arg in ("all", "size"):
        for size in (0, 1080, 800, 640, 540):
            configs.append((f"max_size={size or 'native'}", {"max_size": size}))
    if arg in ("all", "encoder"):
        for enc in (None, "c2.qti.avc.encoder", "c2.android.avc.encoder"):
            configs.append((f"encoder={enc or 'default'}", {"max_size": 640, "encoder": enc}))

    results = [r for r in (run(label, kw) for label, kw in configs) if r]

    print("\n\n== summary ==")
    print(
        f"{'config':<30}{'size':>12}{'start':>9}{'grab':>9}"
        f"{'lag':>9}{'ocr':>9}{'match1':>9}{'matchN':>9}"
    )
    for r in results:
        lag = f"{r['lag']:.0f}" if r["lag"] else "n/a"
        print(
            f"{r['label']:<30}{r['size'][0]}x{r['size'][1]:<7}"
            f"{r['startup']:>8.0f} {r['grab']:>8.1f} {lag:>8} "
            f"{r['ocr']:>8.0f} {r['match_first']:>8.0f} {r['match_cached']:>8.0f}"
        )
