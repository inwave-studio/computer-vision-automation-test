import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
from autoplay import session
s = session()
f = s.frame(fresh=True)
for eid in ("panel-close","settings-close","close-popup","star-hud"):
    h = s.matcher.find(f, eid, max_results=3)
    print(f"{eid:16s}", [(x.center, round(x.score,3)) for x in h])
