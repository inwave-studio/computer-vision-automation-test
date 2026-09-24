"""Accuracy vs downscale, isolated from streaming (design.md task 3, bullet 1).

Captures native frames of the screens the testcase actually has to read, then
replays OCR and template matching against downscaled copies. No app timing, so
a miss here is genuinely a resolution limit and not a race.
"""

import sys
import time

import cv2

from autoplay.device import Device
from autoplay.screen import Screen
from autoplay.session import find_database
from autoplay.vision import TemplateMatcher, TextFinder

APP = "com.amanotes.beathopper"
# (file, needles that must still be read, template that must still match)
SHOTS = [
    ("shot_prompt.png", ["thông báo", "Cho phép"], None),
    ("shot_genre.png", ["POP"], None),
]


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
        frame = screen.latest()
        if text.find(frame, "Cho phép"):
            cv2.imwrite("shot_prompt.png", frame)
            print("captured shot_prompt.png", frame.shape)
            el = text.find(frame, "Cho phép")
            x, y = screen.to_device(*el.center)
            device.tap(x, y)
            break
        time.sleep(0.3)

    end = time.time() + 60
    while time.time() < end:
        frame = screen.latest()
        if text.find(frame, "POP"):
            cv2.imwrite("shot_genre.png", frame)
            print("captured shot_genre.png", frame.shape)
            break
        time.sleep(0.3)
    screen.stop()


def probe(long_edges):
    db, db_dir = find_database(".")
    text = TextFinder()
    for path, needles, template in SHOTS:
        frame = cv2.imread(path)
        if frame is None:
            print(f"{path}: missing, run with --capture first")
            continue
        h, w = frame.shape[:2]
        print(f"\n== {path}  native {w}x{h} ==")
        for edge in long_edges:
            scale = 1.0 if edge == 0 else min(1.0, edge / float(max(w, h)))
            img = frame if scale == 1.0 else cv2.resize(
                frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
            )
            t = time.time()
            hits = [n for n in needles if text.find(img, n)]
            ocr_ms = (time.time() - t) * 1000.0
            mark = "ok " if len(hits) == len(needles) else "MISS"
            line = (f"  max_size={edge:<5} {img.shape[1]}x{img.shape[0]:<6} "
                    f"ocr {len(hits)}/{len(needles)} {mark} {ocr_ms:6.0f}ms")
            if template:
                m = TemplateMatcher(db, base_dir=db_dir)
                t = time.time()
                found = m.find(img, template)
                line += f"  match {len(found)} in {(time.time()-t)*1000.0:6.0f}ms"
            print(line)
            for n in needles:
                if n not in hits:
                    print("        missed: " + n.encode("ascii", "replace").decode())


if __name__ == "__main__":
    if "--capture" in sys.argv:
        capture()
    edges = [int(a) for a in sys.argv[1:] if a.isdigit()] or [0, 1600, 1400, 1200, 1000, 800, 640]
    probe(edges)
