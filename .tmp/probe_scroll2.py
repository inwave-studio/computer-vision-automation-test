import os, sys, cv2
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".agent", "Smoke"))
from common import *
open_app(app_id)
print("home:", reach_home())
d = session().device
f0 = session().frame(fresh=True)
t0 = {e.text for e in session().text.read_all(f0)}
for i in range(4):
    d.swipe(d.width // 2, int(d.height * 0.85), d.width // 2, int(d.height * 0.45), 400)
    wait(1_200)
    f = session().frame(fresh=True); cv2.imwrite(f".tmp/shots/sd{i+1}.png", f)
    t = {e.text for e in session().text.read_all(f)}
    print(i, "new:", len(t - t0), sorted(t - t0)[:5], "focus:", d.focused_activity().split(".")[-1])
