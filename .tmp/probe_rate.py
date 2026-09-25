import os, sys, cv2
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".agent", "Smoke"))
from common import *
open_app(app_id)
print("setting:", open_setting())
tap(findText(["Đánh giá", "Rate us"], 0))
for i in range(6):
    wait(1_000)
    print(i, session().device.focused_activity())
f = session().frame(fresh=True)
cv2.imwrite(".tmp/shots/rate544.png", f)
