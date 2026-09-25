import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
from autoplay import session
s = session()
f = s.frame(fresh=True)
for th in (0.75, 0.88, 0.9, 0.92):
    h = s.matcher.find(f, "panel-close", threshold=th, max_results=5)
    print(f"panel-close th={th}", [(x.center, round(x.score,3)) for x in h])
print("settings-close:", [(x.center, round(x.score,3)) for x in s.matcher.find(f,"settings-close",max_results=3)])
