"""Dismiss whatever is on screen, open the Ball tab, and save a screenshot."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
from autoplay import session
import cv2

s = session()

for _ in range(4):
    if find("star-hud", 0) and find("settings-button", 0):
        break
    shut = find("close-popup", 0) or find("panel-close", 0, threshold=0.88) or find("settings-close", 0)
    if shut:
        tap(shut)
    wait(2000)

print("home reached:", bool(find("star-hud", 0)))

tab = find("tab-ball", 0)
print("tab-ball:", tab)
if tab:
    tap(tab)
    wait(4000)

for _ in range(2):
    shut = find("close-popup", 0)
    if not shut:
        break
    tap(shut); wait(2000)

f = s.frame(fresh=True)
os.makedirs(".tmp/shots", exist_ok=True)
cv2.imwrite(".tmp/shots/ball.png", f)
small = cv2.resize(f, None, fx=0.85, fy=0.85)
cv2.imwrite(".tmp/shots/ball-s.png", small)
print("frame", f.shape, "focus:", s.device.focused_activity())
for name in ("ball-equipped", "ball-lock"):
    for th in (0.6, 0.7, 0.75, 0.85):
        h = s.matcher.find(f, name, threshold=th, max_results=6)
        print(f"  {name} th={th}: ", [(x.center, round(x.score,3)) for x in h])
