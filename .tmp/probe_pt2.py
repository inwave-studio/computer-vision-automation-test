import sys, time
sys.path.insert(0, r"D:\Projects\AndroidAutoBot")
from autoplay import *
from autoplay import session
import cv2
def shot(n):
    f = session().frame(fresh=True); cv2.imwrite(f".tmp/shots/pt_{n}.png", f)
    print("SHOT", n, round(time.monotonic()-T0), [e.text for e in session().text.read_all(f)][:30])
T0 = time.monotonic()
shot("2_state")
tap(norm(153/544, 92/1200)); wait(800); shot("3_ticked")
tap(find("btnAutoplayClose")[0]); wait(1000); shot("4_closed")
wb = find("white-ball")
tap(wb); wait(1000)
for i in range(16):
    wait(4000); shot(f"5_{i:02d}")
