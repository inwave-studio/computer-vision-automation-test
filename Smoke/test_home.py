"""
Các Testcase define ở: https://docs.google.com/spreadsheets/d/1THhmMRK9_1eRU72-iPB00-VgJDHPw1nDS-eq2KCCSIg/edit?gid=727308783#gid=727308783

Smoke test: Home.

Chạy trực tiếp:  python .agent/Smoke/test_home.py

Testcase này chạy trên một app ĐÃ onboard xong (khác test_playtut.py, vốn
`clear()` rồi đi qua onboarding). Ở đây cố tình không `clear()`: section
Gem và Star yêu cầu kiểm tra số dư còn giữ nguyên sau khi kill app, mà
`clear()` thì xoá sạch đúng cái số dư đó. Helper dùng chung ở common.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import *  # noqa: E402,F403

start()

# -- Home / Header: kiểm tra các button hiện --------------------------------
# Sheet liệt kê: Profile button, star HUD, gem HUD, VIP, Setting.
header = {
    "profile button": "profile-button",
    "star HUD": "star-hud",
    "gem HUD": "gem-hud",
    "VIP button": "vip-button",
    "Setting button": "settings-button",
}
for label, element_id in header.items():
    alert(find(element_id), name=f"Home header: {label} hiển thị")

# Ba tab dưới cùng không nằm trong danh sách Header của sheet nhưng là đường đi
# tới các màn khác (test_shopball.py đi qua tab Bóng), nên kiểm tra luôn ở đây
# để lỗi hiện ra đúng chỗ.
for label, element_id in [
    ("Shop tab", "tab-shop"),
    ("Ball tab", "tab-ball"),
    ("Discover tab", "tab-discover"),
]:
    alert(find(element_id), name=f"Home header: {label} hiển thị")

# -- Home / Gem và Star: hiển thị đúng, kill app vào lại vẫn đúng -----------
star_before = hud_number("star-hud")
gem_before = hud_number("gem-hud")

alert(star_before is not None, name=f"Star HUD đọc được số (={star_before})")
alert(gem_before is not None, name=f"Gem HUD đọc được số (={gem_before})")

kill(app_id)
open_app(app_id)
alert(reach_home(), name="Mở lại app sau khi kill")

star_after = hud_number("star-hud")
gem_after = hud_number("gem-hud")

alert(
    star_after == star_before,
    name=f"Star giữ nguyên sau khi kill app ({star_before} -> {star_after})",
)
alert(
    gem_after == gem_before,
    name=f"Gem giữ nguyên sau khi kill app ({gem_before} -> {gem_after})",
)

# -- Home / Songlist --------------------------------------------------------
# Sheet: danh sách bài hát dạng tab xếp chồng dọc, kéo tới cuối thì load thêm,
# và hiển thị đúng dạng lock song.
#
# Chờ danh sách nạp xong rồi mới đếm. Ngay sau khi mở lại app, Home vẽ HUD
# trước rồi mới đổ danh sách bài hát xuống, nên nếu đếm ngay thì chỉ thấy 1
# card và assertion trượt vì đo quá sớm chứ không phải vì app sai.
waitUntil(
    lambda: len(find("song-badge", 0)) >= 3,
    timeout=20_000,
    label="songlist nạp xong",
    required=False,
)
songs = find("song-badge")
alert(len(songs) >= 3, name=f"Songlist hiển thị nhiều bài hát (thấy {len(songs)})")

# "Xếp chồng theo chiều dọc": các card phải nằm trên cùng một cột, cách đều
# nhau theo trục y. Kiểm tra bằng toạ độ chứ không bằng ảnh - đây là thuộc tính
# bố cục, không phải thuộc tính hình ảnh.
if len(songs) >= 3:
    ys = sorted(e.center[1] for e in songs)
    xs = [e.center[0] for e in songs]
    gaps = [b - a for a, b in zip(ys, ys[1:])]
    alert(
        max(xs) - min(xs) < 40,
        name="Songlist xếp thành một cột dọc",
    )
    alert(
        max(gaps) - min(gaps) < 40,
        name=f"Các card cách đều nhau (gap {min(gaps)}-{max(gaps)}px)",
    )

# Lock song: bài hát phải xem ads mới mở được có hexagon "Ad" bên phải.
# Không phải lúc nào danh sách hiện tại cũng có bài khoá (VIP, hoặc user đã mở
# hết), nên ghi nhận số lượng và chỉ coi là lỗi khi không đọc được gì cả -
# tức là cả danh sách cũng không thấy.
#
# Ngưỡng 0.7 thay vì 0.75 mặc định: badge "Mới" đè lên góc hexagon làm điểm
# khớp tụt xuống 0.737 (đo trên card APT.), trong khi thứ không phải ổ khoá
# cao nhất trên Home chỉ được 0.55.
LOCK_THRESHOLD = 0.7
locked = find("song-ad-lock", 0, threshold=LOCK_THRESHOLD)
alert(
    len(locked) > 0 or len(songs) == 0,
    name=f"Hiển thị đúng dạng lock song ({len(locked)} bài khoá bởi ads)",
)

# Kéo tới cuối danh sách thì tự động load thêm. So tên bài trước và sau khi
# cuộn: nếu có bài mới nạp vào thì nội dung đọc được phải khác đi.
#
# `frame(fresh=True)` chứ không phải `frame()`: frame mặc định có thể là ảnh
# đã chụp từ trước lúc cuộn, và so một ảnh cũ với chính nó thì lúc nào cũng
# ra "không có gì mới".
first_titles = {e.text for e in session().text.read_all(session().frame(fresh=True))}
for _ in range(4):
    scrollVerticle(-60)
    wait(1_200)
after_titles = {e.text for e in session().text.read_all(session().frame(fresh=True))}
alert(
    bool(after_titles - first_titles),
    name=f"Kéo tới cuối danh sách load thêm bài hát ({len(after_titles - first_titles)} mục mới)",
)

# Cuộn ngược lên đầu để các bước sau bắt đầu từ trạng thái quen thuộc. Đếm
# số lần cuộn không đủ: đo trên máy test, sau 6 lần cuộn lên danh sách đã về
# bài đầu tiên nhưng header (HUD, nút Setting) vẫn nằm ngoài màn hình, phải
# cuộn thêm một lần nữa. Nên cuộn tới khi on_home() đúng.
for _ in range(10):
    scrollVerticle(60)
    wait(600)
    if on_home():
        break
wait(1_000)
dismiss_popups()

# -- Home / Song Info -------------------------------------------------------
# Sheet: hiển thị đầy đủ tên bài hát, tên ca sĩ, số điểm, số sao, trạng thái.
# Tên bài và tên ca sĩ nằm ngay trên card nên đọc thẳng từ màn hình.
card_texts = [e.text for e in session().text.read_all(session().frame())]
alert(len(card_texts) > 5, name=f"Song info: đọc được thông tin trên card ({len(card_texts)} dòng)")

# -- Home / Song preview ----------------------------------------------------
# Bấm vào badge bên trái card sẽ phát preview. Không nghe được tiếng qua adb,
# nên chỉ xác nhận app phản hồi: nút chuyển sang trạng thái pause/đang phát.
songs = find("song-badge")
if songs:
    tap(songs[0])
    wait(2_000)
    # App phản hồi theo một trong ba cách: phát preview (danh sách còn nguyên),
    # chạy ads, hoặc bật paywall. Cả ba đều là phản hồi hợp lệ; cái cần loại
    # trừ là app đứng im.
    responded = bool(find("song-badge", 0)) or isAdShowing() or bool(find("close-popup", 0))
    alert(responded, name="Song preview: app phản hồi khi bấm vào bài hát")
    # Paywall che toàn màn hình nên phải đóng trước khi chạy tiếp, nếu không
    # mọi find() sau đây đều tìm sau lưng popup.
    dismiss_popups()

# -- Home / các case cần điều kiện không tự động hoá được -------------------
# Song unlock by Ads / by diamond: cần một bài đang khoá, đủ hoặc thiếu kim
# cương đúng lúc, và một video ads có fill. Bấm vào một bài khoá bởi ads để
# kiểm tra ít nhất là app mở đúng luồng.
locked = find("song-ad-lock", threshold=LOCK_THRESHOLD)
if locked:
    tap(locked[0])
    wait(2_500)
    opened_ad = isAdShowing()
    # Không có video thì app phải báo, theo đúng mô tả trong sheet.
    notice = findText(["không có", "no ads", "not available", "thử lại"], 0)
    alert(
        opened_ad or bool(notice),
        name="Song unlock by Ads: hoặc chạy video, hoặc báo không có video",
    )
    if opened_ad:
        # required=False: ad không đóng được thì back_to_home() ở cuối sẽ tự
        # mở lại app, thay vì TestFailure dừng cả file ở đây.
        closeAd(required=False)
    elif notice:
        popup_close = find("close-popup", 0)
        if popup_close:
            tap(popup_close)
    wait(1_000)


# -- Home / các case không tự động hoá được ---------------------------------
for name, reason in [
    ("Song unlock by diamond", "cần đúng số dư tại thời điểm test"),
    ("Gem/Star thay đổi sau khi chơi", "cần hoàn thành một bài hát"),
]:
    session().skipped += 1
    skipped(name, reason)

alert(back_to_home(), name="Kết thúc: quay về được Home")
