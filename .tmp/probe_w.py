import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
from autoplay import session
s = session()
f = s.frame(fresh=True)
for eid in ("star-hud","gem-hud"):
    h = s.matcher.find(f, eid, max_results=1)
    if not h: print(eid,"no match"); continue
    x1,y1,x2,y2 = h[0].bounds
    for w in (60,80,100,120,160):
        print(f"{eid:9s} w={w:3d} -> {ascii(readText((x1,y1,x2+w,y2)))}")
