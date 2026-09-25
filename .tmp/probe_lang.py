import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".agent", "Smoke"))
from common import *
import cv2
open_app(app_id)
print("home:", reach_home())
print("setting:", open_setting())
row = findText(["Ngôn ngữ", "Language"], 0)
print("row:", row)
tap(row); wait(2_500)
f = session().frame(fresh=True)
cv2.imwrite(".tmp/shots/lang544.png", f)
for e in session().text.read_all(f):
    print(repr(e.text), e.bounds)
m = session().matcher
for eid in ("panel-close", "close-popup", "settings-close"):
    print(eid, [(x.center, round(x.score, 3)) for x in m.find(f, eid, threshold=0.6, max_results=3)])
