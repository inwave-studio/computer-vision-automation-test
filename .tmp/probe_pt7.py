import sys
sys.path.insert(0, r"D:\Projects\AndroidAutoBot")
from autoplay import *
from autoplay import session
import cv2
f = session().frame(fresh=True); cv2.imwrite(".tmp/shots/px_00.png", f)
print("SHOT", session().device.focused_activity(), [e.text for e in session().text.read_all(f)][:30])
