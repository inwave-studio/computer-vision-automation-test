import os, sys, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
from autoplay import session
app_id = "com.amanotes.beathopper"
open_app(app_id)
s = session()
for i in range(12):
    f = s.frame()
    hits = s.matcher.find(f, "close-popup", max_results=3)
    star = s.matcher.find(f, "star-hud", max_results=1)
    print(f"i={i} frame_mean={f.mean():.1f} close-popup={[(h.center,round(h.score,2)) for h in hits]} star={len(star)}")
    cv2.imwrite(f'.tmp/shots/reach-{i}.png', f)
    wait(2_000)
