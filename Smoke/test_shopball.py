"""
Các Testcase define ở: https://docs.google.com/spreadsheets/d/1THhmMRK9_1eRU72-iPB00-VgJDHPw1nDS-eq2KCCSIg/edit?gid=727308783#gid=727308783

Smoke test: Shop Ball.

Chạy trực tiếp:  python .agent/Smoke/test_shopball.py

Testcase này chạy trên một app ĐÃ onboard xong (khác test_playtut.py, vốn
`clear()` rồi đi qua onboarding). Các case cần mua VIP, đủ diamond thật,
hoặc một event đang chạy thì ghi SKIP kèm lý do. Helper dùng chung ở common.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import *  # noqa: E402,F403

start()

alert(open_ball_tab(), name="Mở được tab Shop Ball")

# -- Ball - preview ---------------------------------------------------------
# Sheet: hiển thị ball đang trang bị hoặc chọn xem trước. Dấu tick xanh nằm
# trên đúng một quả bóng - quả đang trang bị.
equipped = find("ball-equipped")
alert(len(equipped) == 1, name=f"Ball preview: đúng một quả đang trang bị ({len(equipped)})")

# -- Ball - unlock by Ads / by diamond: trạng thái khoá ---------------------
# ball-lock là ổ khoá nhỏ, độ tương phản thấp; ở ngưỡng mặc định 0.75 nó bắt
# nhầm cả chrome của HUD. 0.85 là ngưỡng đo được trên lưới ball: giữ 7 ổ khoá
# thật, và không bắt gì trên màn Home vốn không có ổ khoá nào - xem chú thích
# trong element-database.py.
locks = find("ball-lock", threshold=0.85)
alert(len(locks) > 0, name=f"Shop Ball hiển thị ball đang khoá ({len(locks)} quả)")

# -- Ball - Chọn nhanh ------------------------------------------------------
# Sheet: bấm 2 lần vào ball để chọn nhanh ball sở hữu. Quả đang trang bị là
# quả chắc chắn sở hữu, nên dùng chính nó làm mục tiêu - không cần suy ra quả
# nào mở khoá từ vị trí ổ khoá.
owned = find("ball-equipped", 0)
if owned:
    # Double tap vào quả đang trang bị: theo mô tả thì thao tác này chọn nhanh
    # quả đang sở hữu, và app phải giữ nguyên trạng thái trang bị chứ không
    # rơi vào popup mua bán.
    doubleTap(owned[0])
    wait(2_000)
    alert(
        find("ball-equipped", 0),
        name="Ball - Chọn nhanh: double tap vào ball sở hữu giữ trạng thái trang bị",
    )

# -- Ball - purchase (diamond) ---------------------------------------------
# Sheet: bấm vào ball khoá -> hiện giá bằng diamond; không đủ thì bắn popup
# shop currency. Máy test đang có 35 gem nên nhánh "không đủ" là nhánh chạy
# được; nhánh mua thành công cần số dư thật nên chỉ ghi nhận khi gặp.
locks = find("ball-lock", threshold=0.85)
if locks:
    tap(locks[0])
    wait(2_500)
    shop_popup = findText(["kim cương", "GEM PACKS", "diamond", "Không đủ", "not enough"], 0)
    # Không dùng needle ngắn kiểu "Xem": findText bỏ dấu rồi so CHUỖI CON, nên
    # "xem" dính luôn vào "Xem tất cả các gói" của paywall - case sẽ xanh vì
    # một popup chẳng liên quan gì tới việc mở khoá ball.
    watch_ad = findText(["xem quảng cáo", "watch ad", "xem video"], 0)
    alert(
        bool(shop_popup) or bool(watch_ad) or isAdShowing(),
        name="Ball khoá: mở popup mua bằng diamond hoặc unlock bằng ads",
    )
    if isAdShowing():
        # required=False: xem chú thích tương ứng trong test_home.py.
        closeAd(required=False)
    else:
        back = find("close-popup", 0) or find("settings-close", 0)
        if back:
            tap(back)
            wait(1_500)

# -- Các case không tự động hoá được ---------------------------------------
# Ghi nhận rõ ràng thay vì bỏ qua im lặng, để báo cáo phản ánh đúng phạm vi
# đã chạy: các case sau cần thanh toán thật hoặc một sự kiện đang diễn ra.
for name, reason in [
    ("Ball - unlock by VIP", "cần mua VIP thật"),
    ("Ball - obtain via special events", "cần event đang chạy"),
    ("Ball - purchase thành công", "cần đủ diamond / IAP sandbox"),
]:
    session().skipped += 1
    skipped(name, reason)

alert(back_to_home(), name="Kết thúc: quay về được Home")
