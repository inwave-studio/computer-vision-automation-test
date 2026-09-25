"""Fresh process: templates are read from disk on first use, so this sees the
new crops (the re-crop script had already cached the old ones in-process)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoplay import *
from autoplay import session
s = session()
f = s.frame(fresh=True)
for name in ("ball-equipped", "ball-lock"):
    for th in (0.75, 0.85, 0.9):
        h = s.matcher.find(f, name, threshold=th, max_results=20)
        print(f"  {name} th={th}: {len(h)} {[round(x.score,3) for x in h][:12]}")
