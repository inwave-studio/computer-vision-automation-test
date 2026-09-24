"""Which video encoder is best? (design.md task 3, bullet 3)

What matters for a test harness is how old the newest frame is when a step
reads it, so this measures glass-to-frame lag per encoder, plus how long the
stream takes to come up (paid once per run).
"""

import statistics
import sys
import time

from autoplay.device import Device
from autoplay.screen import Screen
from bench_lag import lag_once

ENCODERS = [None, "c2.qti.avc.encoder", "c2.android.avc.encoder", "c2.qti.hevc.encoder"]


def run(encoder, rounds=5):
    device = Device()
    t = time.time()
    screen = Screen(device, encoder=encoder)
    screen.start()
    startup = (time.time() - t) * 1000.0
    name = encoder or "(scrcpy default)"
    if not screen._streaming:
        print(f"{name:<26} stream failed")
        screen.stop()
        return
    frame = screen.latest()
    lags = []
    for _ in range(rounds):
        ms = lag_once(device, screen)
        if ms is not None:
            lags.append(ms)
    screen.stop()
    if not lags:
        print(f"{name:<26} no lag samples")
        return
    h, w = frame.shape[:2]
    print(f"{name:<26} {w}x{h:<6} startup {startup:6.0f}ms  "
          f"lag median {statistics.median(lags):6.0f}ms  min {min(lags):5.0f}  max {max(lags):5.0f}")


if __name__ == "__main__":
    print(f"{'encoder':<26} {'frame':<11} {'startup':>13}  lag")
    for e in (sys.argv[1:] or ENCODERS):
        run(None if e in (None, "default") else e)
