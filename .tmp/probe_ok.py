import os, sys, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
from autoplay import session
m = session().matcher
for shot in ("gs544", "lang544", "settings", "home544", "ball544", "now4s"):
    f = cv2.imread(f".tmp/shots/{shot}.png")
    print(shot, f.shape[1], [(x.center, round(x.score, 3)) for x in m.find(f, "panel-ok", threshold=0.5, max_results=2)])
