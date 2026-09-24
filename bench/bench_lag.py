"""Glass-to-frame latency: how long after a device-side change does the stream show it?

Triggers a large, instant visual change (the notification shade) and polls the
stream until the frame actually differs.
"""

import statistics
import sys
import time

import cv2
import numpy as np

from autoplay.device import Device
from autoplay.screen import Screen


def lag_once(device, screen, settle=1.0, debug=False):
    device.shell("cmd statusbar collapse")
    time.sleep(settle)
    before = screen.latest()
    t0 = time.time()
    device.shell("cmd statusbar expand-notifications")
    sent = time.time()
    best = 0.0
    hit = None
    while time.time() - t0 < 3.0:
        frame = screen.latest()
        if frame.shape != before.shape:
            continue
        diff = float(np.mean(cv2.absdiff(frame, before)))
        best = max(best, diff)
        if diff > 8.0:
            hit = (time.time() - sent) * 1000.0
            break
    device.shell("cmd statusbar collapse")
    time.sleep(0.5)
    if debug:
        print(f"      max diff seen {best:.1f}  -> {hit}")
    return hit


def run(label, **kw):
    device = Device()
    screen = Screen(device, **kw)
    screen.start()
    if not screen._streaming:
        print(f"{label}: stream failed")
        screen.stop()
        return
    f = screen.latest()
    lags = []
    for i in range(6):
        v = lag_once(device, screen, debug=(i == 0))
        if v is not None:
            lags.append(v)
    h, w = f.shape[:2]
    if lags:
        print(
            f"{label:<38} {w}x{h:<6}  lag median {statistics.median(lags):6.0f}ms  "
            f"min {min(lags):5.0f}  max {max(lags):5.0f}  n={len(lags)}"
        )
    else:
        print(f"{label:<38} {w}x{h:<6}  no change detected")
    screen.stop()


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "fps"
    if which == "fps":
        for fps in (15, 30, 60):
            run(f"max_size=800 fps={fps}", max_size=800, max_fps=fps)
    elif which == "size":
        for size in (0, 800):
            run(f"max_size={size} fps=30", max_size=size, max_fps=30)
