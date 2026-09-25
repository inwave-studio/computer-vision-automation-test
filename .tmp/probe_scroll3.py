import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".agent", "Smoke"))
from common import *
open_app(app_id)
print("home:", reach_home())
for _ in range(6):
    scrollVerticle(60); wait(400)
t0 = {e.text for e in session().text.read_all(session().frame(fresh=True))}
for _ in range(4):
    scrollVerticle(-60); wait(1_200)
t1 = {e.text for e in session().text.read_all(session().frame(fresh=True))}
print("down new:", len(t1 - t0))
for _ in range(6):
    scrollVerticle(60); wait(400)
wait(1_500)
t2 = {e.text for e in session().text.read_all(session().frame(fresh=True))}
print("back at top overlap with start:", len(t2 & t0), "/", len(t0), "on_home:", on_home())
