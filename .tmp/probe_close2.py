import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
from autoplay import session
s = session()
print("before:", s.device.focused_activity())
print("closeAd ->", s.closeAd(timeout=60_000, required=False))
print("after:", s.device.focused_activity())
