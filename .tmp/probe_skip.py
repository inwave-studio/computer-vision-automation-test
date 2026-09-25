import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
print("closed:", closeAd(timeout=60_000, required=False))
