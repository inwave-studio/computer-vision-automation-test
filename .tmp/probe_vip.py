import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
from autoplay import session
import cv2
s = session()
f = s.frame(fresh=True)
cv2.imwrite('.tmp/shots/frame544.png', f)
for eid in ("vip-mission","vip-button","star-hud","gem-hud","profile-button"):
    hits = s.matcher.find(f, eid, max_results=3)
    print(f"{eid:16s}", [(h.center, round(h.score,3)) for h in hits])
    print("   best score any:", round(s.matcher.score(f, eid), 3) if hasattr(s.matcher,'score') else "n/a")
