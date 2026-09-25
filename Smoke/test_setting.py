"""
Các Testcase define ở: https://docs.google.com/spreadsheets/d/1THhmMRK9_1eRU72-iPB00-VgJDHPw1nDS-eq2KCCSIg/edit?gid=727308783#gid=727308783

Smoke test: Setting.

Chạy trực tiếp:  python .agent/Smoke/test_setting.py

Testcase này chạy trên một app ĐÃ onboard xong (khác test_playtut.py, vốn
`clear()` rồi đi qua onboarding). Helper dùng chung ở common.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import *  # noqa: E402,F403

start()

alert(open_setting(), name="Mở được màn hình Setting")

# Bảy dòng trong sheet. Mỗi dòng là text nên kiểm tra bằng OCR, không cần
# template: nhãn đổi theo ngôn ngữ còn icon thì không, và chính nhãn mới là
# thứ testcase quan tâm.
setting_rows = {
    "SHOP": ["Cửa hàng", "Shop"],
    "GAME SETTINGS": ["Cài đặt trò chơi", "Game settings"],
    "LANGUAGE": ["Ngôn ngữ", "Language"],
    "RATE US": ["Đánh giá", "Rate us"],
    "HOW TO PLAY": ["Hướng dẫn", "How to play"],
    "POLICY": ["Chính sách", "Policy", "Privacy"],
    "CREDIT": ["Giới thiệu", "Credit", "About"],
}
for label, needles in setting_rows.items():
    alert(findText(needles, 0), name=f"Setting hiển thị dòng {label}")

# Setting - CREDIT: hiển thị version hiện tại của game. Số version nằm ngay
# dưới nhãn GIỚI THIỆU, và phải khớp với version adb báo cáo.
credit = findText(["Giới thiệu", "Credit", "About"], 0)
if credit:
    x1, y1, x2, y2 = credit.bounds
    shown = readText((x1, y1, x2 + 500, y2 + 90))
    alert(
        any(c.isdigit() for c in shown),
        name=f"Setting - CREDIT hiển thị version ({shown!r})",
    )


# Setting - SHOP: mở shop iap. Shop là màn hình riêng chứ không phải panel con
# nên đóng bằng nút close của chính nó.
if open_setting():
    shop_row = findText(["Cửa hàng", "Shop"], 0)
    if shop_row:
        tap(shop_row)
        wait(2_500)
        alert(
            findText(["GEM PACKS", "kim cương", "DAILY DEALS"], 0),
            name="Setting - SHOP mở màn hình shop IAP",
        )
        shop_close = find("close-popup", 0) or find("settings-close", 0)
        if shop_close:
            tap(shop_close)
            wait(1_500)

setting_row(
    "GAME SETTINGS hiển thị cài đặt âm thanh/nhạc nền",
    ["Cài đặt trò chơi", "Game settings"],
    ["Âm thanh", "Nhạc", "Sound", "Music", "SFX"],
)
# LANGUAGE chỉ kiểm tra danh sách có mở ra, KHÔNG bấm chọn ngôn ngữ nào. Đổi
# ngôn ngữ là đổi trạng thái của app cho mọi case chạy sau: mọi nhãn tiếng
# Việt trong script sẽ tìm không ra, và máy test nằm lại ở ngôn ngữ khác sau
# khi chạy xong. Nhận diện bằng các mục luôn có trong danh sách.
setting_row(
    "LANGUAGE mở danh sách ngôn ngữ",
    ["Ngôn ngữ", "Language"],
    ["Portugu", "Deutsch", "English"],
)
# HOW TO PLAY mở một màn riêng, tiêu đề "HƯỚNG DẪN CHƠI". Không dùng "Cách
# chơi" làm bằng chứng: đó là dòng phụ của chính dòng HƯỚNG DẪN trên màn
# Setting, nên case sẽ xanh cả khi bấm vào mà không có gì mở ra. "Hướng dẫn
# chơi" thì không khớp nhầm "HƯỚNG DẪN" - findText so chuỗi con theo chiều
# needle nằm trong nhãn, không phải ngược lại.
setting_row(
    "HOW TO PLAY hiển thị popup hướng dẫn",
    ["Hướng dẫn", "How to play"],
    ["Hướng dẫn chơi", "Giữ và kéo", "điều khiển"],
)

# Setting - RATE US và POLICY đều rời khỏi app: một cái mở store, một cái mở
# trình duyệt. Kiểm tra bằng activity đang focus chứ không bằng hình ảnh - sau
# khi nhảy sang app khác thì template của game không còn ý nghĩa gì nữa.
leaves_app("RATE US chuyển sang store", ["Đánh giá", "Rate us"])
leaves_app(
    "POLICY mở trang web",
    ["Chính sách", "Policy", "Privacy"],
    extra=["policy", "privacy", "chính sách"],
)

# Đóng Setting, về Home.
close = find("settings-close", 0)
if close:
    tap(close)
    wait(1_500)
alert(back_to_home(), name="Kết thúc: quay về được Home")
