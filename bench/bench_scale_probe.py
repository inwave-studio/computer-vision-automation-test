"""Isolate matching from streaming: capture one native popup frame, then match
downscaled copies of it. Removes app timing from the question entirely."""

import time

import cv2

from autoplay.device import Device
from autoplay.screen import Screen
from autoplay.session import find_database
from autoplay.vision import TemplateMatcher, TextFinder

APP = "com.amanotes.beathopper"


def capture():
    device = Device()
    screen = Screen(device, max_size=0)
    screen.start()
    text = TextFinder()
    device.kill_app(APP)
    device.clear_app(APP)
    device.open_app(APP)

    end = time.time() + 40
    while time.time() < end:
        el = text.find(screen.latest(), "Cho phép")
        if el:
            x, y = screen.to_device(*el.center)
            device.tap(x, y)
            break
        time.sleep(0.3)

    db, db_dir = find_database(".")
    matcher = TemplateMatcher(db, base_dir=db_dir)
    end = time.time() + 75
    while time.time() < end:
        frame = screen.latest()
        if matcher.find(frame, "close-popup"):
            cv2.imwrite("popup_native.png", frame)
            print("captured popup_native.png", frame.shape)
            screen.stop()
            return frame
        time.sleep(0.3)
    screen.stop()
    print("popup never appeared")
    return None


if __name__ == "__main__":
    frame = cv2.imread("popup_native.png")
    if frame is None:
        frame = capture()
    if frame is None:
        raise SystemExit(1)

    db, db_dir = find_database(".")
    h, w = frame.shape[:2]
    print(f"\nnative {w}x{h}")
    for target_w in (w, 488, 360, 288, 240):
        scale = target_w / float(w)
        img = (
            frame
            if target_w == w
            else cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        )
        m = TemplateMatcher(db, base_dir=db_dir)
        t = time.time()
        hits = m.find(img, "close-popup")
        ms = (time.time() - t) * 1000.0
        cache = list(m._scale_cache.values())
        best = f"score={hits[0].score:.2f} at {hits[0].center}" if hits else "NO MATCH"
        print(f"  {img.shape[1]:>4}x{img.shape[0]:<5} {best:<28} {ms:6.0f}ms  scale={cache}")
