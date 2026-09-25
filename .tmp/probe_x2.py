import os, sys, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
from autoplay import session
f = cv2.imread(sys.argv[1])
m = session().matcher
for eid in ("close-popup", "settings-close", "panel-close", "ad-close"):
    print(eid, [(x.center, round(x.score, 3)) for x in m.find(f, eid, threshold=0.5, max_results=3)])
for e in session().text.read_all(f):
    print(repr(e.text), e.bounds)
for th in (0.75, 0.88):
    print("panel-close th", th, [(x.center, round(x.score, 3)) for x in m.find(f, "panel-close", threshold=th, max_results=3)])
