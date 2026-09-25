import sys, time
sys.path.insert(0, r"D:\Projects\AndroidAutoBot")
from autoplay import *
from autoplay import session
import cv2
T0 = time.monotonic()
def shot(n):
    f = session().frame(fresh=True); cv2.imwrite(f".tmp/shots/pv_{n}.png", f)
    print("SHOT", n, round(time.monotonic()-T0), session().device.focused_activity().split("/")[-1][-30:], [e.text for e in session().text.read_all(f)][:14])
print("closeAd", closeAd(required=False))
for i in range(5):
    wait(2500); shot(f"{i:02d}")
