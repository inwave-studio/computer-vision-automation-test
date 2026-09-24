"""Check the smallest template (close-popup) still matches at reduced stream sizes.

The paywall is transient, so this relaunches the app for each size and waits
for the popup rather than assuming it is already on screen.
"""

import sys
import time

from autoplay.device import Device
from autoplay.screen import Screen
from autoplay.session import find_database
from autoplay.vision import TemplateMatcher

APP = "com.amanotes.beathopper"


def run(size):
    device = Device()
    screen = Screen(device, max_size=size)
    screen.start()
    if not screen._streaming:
        print(f"max_size={size}: stream failed")
        return
    db, db_dir = find_database(".")
    matcher = TemplateMatcher(db, base_dir=db_dir)
    from autoplay.vision import TextFinder

    text = TextFinder()

    device.kill_app(APP)
    device.clear_app(APP)
    device.open_app(APP)

    # The paywall only comes after the notification prompt is dealt with, and
    # this harness streams with control=false, so tap it through adb.
    prompt_deadline = time.time() + 40
    while time.time() < prompt_deadline:
        el = text.find(screen.latest(), "Cho phép")
        if el:
            x, y = screen.to_device(*el.center)
            device.tap(x, y)
            break
        time.sleep(0.3)

    deadline = time.time() + 75
    hit = None
    while time.time() < deadline:
        frame = screen.latest()
        found = matcher.find(frame, "close-popup")
        if found:
            hit = (found[0], frame.shape, matcher._scale_cache)
            break
        time.sleep(0.3)

    if hit:
        el, shape, cache = hit
        scale = list(cache.values())[0]
        print(
            f"max_size={size:<5} frame {shape[1]}x{shape[0]:<5} "
            f"FOUND score={el.score:.2f} at {el.center}  variant/scale={scale}"
        )
    else:
        print(f"max_size={size:<5} NOT FOUND within 75s")
    screen.stop()


if __name__ == "__main__":
    for s in [int(a) for a in sys.argv[1:]] or [0, 800, 640]:
        run(s)
