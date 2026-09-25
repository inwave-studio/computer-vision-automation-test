import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

# -- Chơi hết bài tới result screen -----------------------------------------
# "Add fail point" ở trên bật auto-play của bản build test: bóng rơi một lần ở
# đầu bài (LÀM LẠI NÀO), sau đó tự chơi tới hết mà không hiện màn continue.
# Hết bài thì app chen vào một interstitial, có khi thêm popup "Cảm ơn đã xem
# quảng cáo", rồi mới tới result screen. Thứ tự và loại ad không cố định, nên
# vòng lặp dọn thứ nào đang ở trên cùng cho tới khi thấy result screen.

def song_cards():
    """Các song card đang hiển thị, mỗi card là một cặp (đĩa nhạc, nút phải).

    Một card chỉ được tính khi có ĐỦ hai thứ trên cùng một hàng: icon đĩa nhạc
    ở góc trái (`song-badge`) và hexagon ở góc phải - tím "Ad" (`song-ad-lock`)
    hoặc vàng play (`song-play`). Một template lẻ có thể khớp nhầm vào ảnh bìa,
    nhưng khó mà ảnh bìa nào tạo ra đúng một cặp trái-phải cùng hàng.

    Hai hexagon tìm riêng chứ không gộp làm một element nhiều variant: find()
    trả về các hit của MỘT variant thắng, nên một màn có cả card Ad lẫn card
    play sẽ chỉ đếm được một loại.
    """
    badges = find("song-badge", 0)
    # Ngưỡng đo trên result screen và Home: hexagon Ad thật 0.74-0.96 (badge
    # "Mới" đè lên góc làm tụt điểm), play thật 0.95-1.0, trượt cao nhất 0.73.
    buttons = list(find("song-ad-lock", 0, threshold=0.7)) + list(
        find("song-play", 0, threshold=0.8)
    )
    cards = []
    for badge in badges:
        bx, by = badge.center
        for button in buttons:
            x, y = button.center
            if x > bx + 200 and abs(y - by) < 25:
                cards.append((badge, button))
                break
    return cards


def on_result_screen():
    return bool(findText(["Chơi tiếp", "Đã hoàn thành"], 0)) and bool(song_cards())


def clear_way_to_result():
    """Một bước dọn đường về result screen. Trả về True khi đã tới."""
    if on_result_screen():
        return True
    if isAdShowing():
        activity = session().device.focused_activity() or ""
        if "bigo" in activity.lower():
            # End card của Bigo (CompanionAdActivity) không có nút đóng: nút
            # ">" góc trên là click-through, bấm vào là mở Play Store. Đo trên
            # máy test, chỉ có phím Back đóng được nó, và Back đưa thẳng về
            # result screen. closeAd() cố tình không dùng Back, nên xử lý ở đây.
            session().device.shell("input", "keyevent", "4")
            wait(2_000)
        else:
            closeAd(timeout=60_000, required=False)

        hide(app_id)
        wait(100)
        open_app(app_id)
        return False
    if findText(["Cảm ơn đã xem quảng cáo", "Thanks for watching"], 0):
        # Nút X hexagon dưới popup: settings-close khớp 0.98 trên popup này.
        shut = find("settings-close", 0)
        if shut:
            tap(shut)
            wait(1_500)
    return False


# Bài hướng dẫn dài ~45s, interstitial thêm ~40s nữa.
alert(
    waitUntil(clear_way_to_result, timeout=180_000, label="result screen"),
    name="Chơi hết bài hướng dẫn và tới được result screen",
)

# -- Result screen: cuộn xuống vẫn thấy song card ---------------------------
before = sorted(badge.center[1] for badge, _ in song_cards())
for _ in range(2):
    scrollVerticle(-40)
    wait(1_500)
cards = song_cards()
after = sorted(badge.center[1] for badge, _ in cards)

alert(after != before, name="Result screen cuộn xuống được")
alert(
    len(cards) >= 1,
    name=f"Result screen: sau khi cuộn thấy ít nhất 1 song card ({len(cards)} card)",
)
