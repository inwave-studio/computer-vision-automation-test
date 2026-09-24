"""Beat Hopper first-launch onboarding, up to the tutorial song picker.

Run it directly:  python Tests/test_beathopper_onboarding.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoplay import *  # noqa: E402,F403

app_id = "com.amanotes.beathopper"

stop(app_id)
clear(app_id)
open_app(app_id)

# The notification prompt is optional: Android only asks once, and a re-install
# does not always bring it back. required=False keeps a no-show from failing.
prompt = waitUntil(
    lambda: findText("notifications?") or findText("thông báo"),
    timeout=15_000,
    label="allow notifications prompt",
    required=False,
)

# An optional wait hands back None instead of failing, so the prompt only needs
# dismissing when it actually showed up.
if prompt:
    tap(findText("ALLOW") or findText("Cho phép"))

# The premium offer is another optional interstitial - it depends on the build
# and on remote config, so close it if it shows and carry on if it does not.
paywall = waitUntil(
    lambda: find("close-popup"),
    timeout=10_000,
    label="premium offer popup",
    required=True,
)
if paywall:
    tap(paywall)

tap(waitUntil(lambda: findText("POP"), timeout=10_000, label="genre picker"))

# 'Continue' only appears once a genre is selected, so wait for it rather than
# assuming the animation has finished. The app follows the device language, so
# accept either label. Each OCR poll costs about a second, so a short timeout
# buys only a couple of attempts - 10s to ride out the selection animation.
tap(
    waitUntil(
        lambda: findText("Continue") or findText("Tiếp tục"),
        timeout=10_000,
        label="Continue button",
    )
)
wait(100)

# Dismiss every optional survey step until none is left.
while True:
    skip = findText("Prefer not to say") or findText("Không trả lời")
    if not skip:
        break
    tap(skip)
    wait(500)

chooseTutSongScreen = waitUntil(
    lambda: findText("Let's play your first song") or findText("bài hát đầu tiên của bạn"),
    timeout=5_000,
    label="tutorial song screen",
)

wait(200)

alert(chooseTutSongScreen, name="tutorial song screen is shown")

if chooseTutSongScreen:
    listPlayButtons = find("play-button")
    alert(len(listPlayButtons) >= 4, name=f"at least 4 play buttons (found {len(listPlayButtons)})")
