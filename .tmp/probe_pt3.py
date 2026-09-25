import sys, time
sys.path.insert(0, r"D:\Projects\AndroidAutoBot")
from autoplay import *
from autoplay import session
import cv2
def shot(n):
    f = session().frame(fresh=True); cv2.imwrite(f".tmp/shots/pt_{n}.png", f)
    print("SHOT", n, [e.text for e in session().text.read_all(f)][:40])
tap(find("settings-close")); wait(2500); shot("6_result")
wait(3000); shot("6_result_b")
scrollVerticle(-40); wait(1500); shot("7_scrolled")
scrollVerticle(-40); wait(1500); shot("7_scrolled2")
