import sys
sys.path.insert(0, r"D:\Projects\AndroidAutoBot")
from autoplay import *
print("SHOWING", isAdShowing())
print("FIND", find("ad-close", 0))
closeAd(timeout=20_000, required=False)
wait(2000)
print("AFTER", session().device.focused_activity())
