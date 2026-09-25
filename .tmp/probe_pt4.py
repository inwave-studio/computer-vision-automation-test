import os
import sys
import random

sys.path.insert(0, r"D:\Projects\AndroidAutoBot")

from autoplay import *

app_id = "com.amanotes.beathopper"

stop(app_id)
clear(app_id)
open_app(app_id)

alert(find("splash-screen"), name="splash screen is shown")

# The notification prompt is optional: Android only asks once, and a re-install
# does not always bring it back. required=False keeps a no-show from failing.
prompt = waitUntil(
    lambda: findText(["notifications?","thông báo"], 0),
    timeout=15_000,
    label="allow notifications prompt",
    required=False,
)

# An optional wait hands back None instead of failing, so the prompt only needs
# dismissing when it actually showed up.
if prompt:
    tap(findText(["ALLOW", "Cho phép"]))

# The premium offer is another optional interstitial - it depends on the build
# and on remote config, so close it if it shows and carry on if it does not.
paywall = waitUntil(
    lambda: find("paywall", 0),
    timeout=10_000,
    label="premium offer popup",
    required=False,
)
if paywall:
    tap(find("close-popup"))

waitUntil(lambda: findText(["genre","thể loại"], 0), timeout=10_000, label="genre picker")

genres = find("genre-btn", 5)
alert(len(genres) > 0, name = "Found Genre Buttons")

genreIndex = random.randint(0, len(genres) - 1)
tap(genres[genreIndex])
print(f"TAP GENRE {genreIndex}")

# 'Continue' only appears once a genre is selected, so wait for it rather than
# assuming the animation has finished. The app follows the device language, so
# accept either label. Each OCR poll costs about a second, so a short timeout
# buys only a couple of attempts - 10s to ride out the selection animation.
tap(
    waitUntil(
        lambda: findText(["Continue", "Tiếp tục"], 0),
        timeout=10_000,
        label="Continue button",
    )
)
wait(100)

# Dismiss every optional survey step until none is left.
while True:
    skip = findText(["Prefer not to say", "Không trả lời"], 0)
    if not skip:
        break
    tap(skip)
    wait(500)

chooseTutSongScreen = waitUntil(
    lambda: findText(["Let's play your first song", "bài hát đầu tiên của bạn"], 0),
    timeout=5_000,
    label="tutorial song screen",
)

alert(chooseTutSongScreen, name="tutorial song screen is shown")

if chooseTutSongScreen:
    listPlayButtons = find("play-button")
    alert(len(listPlayButtons) >= 4, name=f"at least 4 play buttons (found {len(listPlayButtons)})")

index = random.randint(0, len(listPlayButtons) - 1)

print(f"tapping play button at index {index} (0-based)")
tap(listPlayButtons[index])

waitUntil(
    lambda: find("tile-normal", 0),
    timeout=10_000,
    label="tutorial gameplay prepare"
)
wait(100)

whiteball = find("white-ball")

alert(len(whiteball) > 0, name="white ball is found")

tap(findText("play"))
wait(100)
tap(findText("Add fail point"))
wait(100)
tap(find("btnAutoplayClose")[0])
wait(100)
# OCR reads the first word of "Giữ và Kéo để Điều khiển" as "Git", so match on
# the part it reads reliably rather than the whole sentence.
alert(
    waitUntil(
        lambda: findText(["Kéo để Điều khiển", "Drag to control"], 0),
        timeout=10_000,
        label="Drag instruction",
        required=False,
    ),
    name="Drag instruction",
)

tap(whiteball)
wait(100)

alert(waitUntil(
    lambda: findText(["Bounce on Tiles", "Nhảy trên VIÊN GẠCH"], 0),
    timeout=10_000,
    label="tutorial gameplay bounce on tiles",
    required=True,
), name="tutorial gameplay bounce on tiles is found") 
import cv2, time
from autoplay import session
T0 = time.monotonic()
def shot(n):
    f = session().frame(fresh=True); cv2.imwrite(f".tmp/shots/pu_{n}.png", f)
    print("SHOT", n, round(time.monotonic()-T0), session().device.focused_activity().split("/")[-1][-30:], [e.text for e in session().text.read_all(f)][:14])
for i in range(20):
    wait(3000); shot(f"{i:02d}")
