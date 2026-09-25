import sys
sys.path.insert(0, r"D:\Projects\AndroidAutoBot")
from autoplay import *
from autoplay import session
import cv2
f = session().frame(fresh=True); cv2.imwrite(".tmp/shots/crackle.png", f)
print("TEXT", [(e.text, e.center) for e in session().text.read_all(f)])
m = session().matcher
for e in ("ad-close", "ad-skip", "close-popup", "event-close", "settings-close", "panel-close"):
    print("TPL", e, [(round(x.score, 3), x.center) for x in m.find(f, e, threshold=0.5, max_results=2)])
