import sys, time
sys.path.insert(0, r"D:\Projects\AndroidAutoBot")
from autoplay import *
from autoplay import session
import cv2
def shot(n):
    f = session().frame(fresh=True); cv2.imwrite(f".tmp/shots/pw_{n}.png", f)
    print("SHOT", n, session().device.focused_activity().split("/")[-1][-30:], [e.text for e in session().text.read_all(f)][:20])
print("isAd", isAdShowing())
print("closeAd", closeAd(required=False))
for i in range(4):
    wait(2500); shot(f"{i:02d}")
