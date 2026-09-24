"""Does removing decoder/socket buffering cut latency? (design.md task 3, bullet 2)

Patches Screen's av.open options and reader drain policy, then measures
glass-to-frame lag for each variant.
"""

import statistics
import sys
import time

import cv2
import numpy as np

import autoplay.screen as screen_mod
from autoplay.device import Device
from autoplay.screen import Screen
from bench_lag import lag_once

VARIANTS = {
    "baseline": dict(options={"probesize": "32", "analyzeduration": "0"}, buffer_size=1 << 16),
    "nobuffer": dict(
        options={
            "probesize": "32",
            "analyzeduration": "0",
            "fflags": "nobuffer",
            "flags": "low_delay",
        },
        buffer_size=1 << 16,
    ),
    "nobuffer+small": dict(
        options={
            "probesize": "32",
            "analyzeduration": "0",
            "fflags": "nobuffer",
            "flags": "low_delay",
        },
        buffer_size=4096,
    ),
}


def patch(variant):
    cfg = VARIANTS[variant]
    orig = screen_mod.av.open

    def patched(source, *args, **kw):
        kw["options"] = cfg["options"]
        kw["buffer_size"] = cfg["buffer_size"]
        return orig(source, *args, **kw)

    screen_mod.av.open = patched
    return orig


def run(variant, rounds=6, **kw):
    orig = patch(variant)
    try:
        device = Device()
        screen = Screen(device, **kw)
        screen.start()
        if not screen._streaming:
            print(f"{variant}: stream failed")
            return
        f = screen.latest()
        lags = [lag_once(device, screen) for _ in range(rounds)]
        lags = [v for v in lags if v is not None]
        h, w = f.shape[:2]
        if lags:
            print(
                f"{variant:<20} {w}x{h:<6} lag median {statistics.median(lags):6.0f}ms "
                f"min {min(lags):5.0f} max {max(lags):5.0f} n={len(lags)}"
            )
        else:
            print(f"{variant:<20} no change detected")
        screen.stop()
    finally:
        screen_mod.av.open = orig


if __name__ == "__main__":
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 800
    for v in VARIANTS:
        run(v, max_size=size, max_fps=30)
