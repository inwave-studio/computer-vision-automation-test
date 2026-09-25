import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
from autoplay import session
s = session()
for i in range(4):
    for eid, w in (("star-hud",160), ("gem-hud",160)):
        hits = s.matcher.find(s.frame(fresh=True), eid, max_results=1)
        if not hits:
            print(i, eid, "NO MATCH"); continue
        e = hits[0]
        x1,y1,x2,y2 = e.bounds
        print(i, eid, "bounds", e.bounds, "->", repr(readText((x1,y1,x2+w,y2))))
    wait(1500)
