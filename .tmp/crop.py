"""Crop template candidates out of a screenshot and report how well each one
matches back against the frame it came from (sanity) and how selective it is."""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SHOT = sys.argv[1] if len(sys.argv) > 1 else ".tmp/shots/now.png"
im = cv2.imread(SHOT)
print("source", SHOT, im.shape)


def crop(name, x1, y1, x2, y2, out_dir="DB/Home"):
    os.makedirs(out_dir, exist_ok=True)
    piece = im[y1:y2, x1:x2]
    path = os.path.join(out_dir, name + ".png")
    cv2.imwrite(path, piece)
    # How many places on this very screen does it match? 1 is what we want.
    res = cv2.matchTemplate(im, piece, cv2.TM_CCOEFF_NORMED)
    hits = int((res >= 0.9).sum())
    print(f"  {path:42s} {piece.shape[1]:4d}x{piece.shape[0]:<4d} hits>=0.9: {hits}")
    return path


if __name__ == "__main__":
    for args in eval(open(".tmp/regions.py").read()):
        crop(*args)
