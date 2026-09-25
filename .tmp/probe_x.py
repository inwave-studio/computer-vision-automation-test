import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
from autoplay import session
import cv2
s = session()
f = s.frame(fresh=True)
cv2.imwrite('.tmp/shots/frame-stall.png', f)
print("frame", f.shape, "focus", s.device.focused_activity())
for eid in ("close-popup","panel-close","settings-close","star-hud"):
    for th in (0.6, 0.7, 0.75):
        h = s.matcher.find(f, eid, threshold=th, max_results=3)
        if h:
            print(f"{eid:15s} th={th} -> {[(x.center, round(x.score,3)) for x in h]}")
            break
    else:
        print(f"{eid:15s} no match even at 0.6")
