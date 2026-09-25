"""
Helper dùng chung cho các smoke test trong thư mục này: test_home.py,
test_setting.py, test_shopball.py.

Testcase define ở: https://docs.google.com/spreadsheets/d/1THhmMRK9_1eRU72-iPB00-VgJDHPw1nDS-eq2KCCSIg/edit?gid=727308783#gid=727308783

Tên file cố tình KHÔNG bắt đầu bằng `test_`: test-runner.py tìm `test_*.py`
và chạy từng file như một testcase, còn file này chỉ là thư viện.

Import file này không tạo session và không đụng tới máy: session của autoplay
chỉ được tạo ở lần gọi API đầu tiên, và lấy tên testcase từ `__main__` - tức
là từ file test đang chạy, không phải từ file này.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from autoplay import *  # noqa: E402,F403
from autoplay import session  # noqa: E402
from autoplay.log import skipped  # noqa: E402,F401

app_id = "com.amanotes.beathopper"

# Nhãn tiếng Anh đi kèm tiếng Việt ở mọi chỗ: app chạy theo ngôn ngữ máy, và
# máy test đang để tiếng Việt. Liệt kê cả hai để script không phụ thuộc locale.
HOME_TAB = ["Trang chủ", "Home"]
SHOP_TAB = ["Cửa hàng", "Shop"]
# Tiêu đề màn Setting. Chỉ nói "đang ở màn Setting", KHÔNG nói "không có gì
# che": panel con chỉ làm tối màn Setting chứ không che kín, OCR vẫn đọc được
# tiêu đề và các dòng bên dưới - xem close_sub_panel().
SETTING_TITLE = ["Cấu hình", "Settings"]
BALL_TAB = ["Bóng", "Ball"]


def hud_number(element_id, width=80):
    """Số hiển thị cạnh icon HUD `element_id`, hoặc None nếu không thấy icon.

    Trả về None thay vì ném lỗi khi icon vắng mặt: vắng icon đã được assertion
    của Header bắt rồi, nên ở đây mà `find(...)[0]` thì chỉ làm cả testcase
    chết bằng IndexError và che mất những case còn lại.
    """
    found = find(element_id, 0)
    return digits(home_hud_value(found[0], width)) if found else None


def home_hud_value(element, width=80):
    """Đọc con số nằm bên phải một icon HUD.

    Số gem/star không nằm trong bounds của icon mà ở ngay cạnh nó, nên phải
    mở rộng vùng đọc sang phải rồi mới OCR. Đọc nguyên icon sẽ ra chuỗi rỗng.

    80px là khoảng đo được trên máy test. Hai pill star và gem nằm sát nhau
    (star kết thúc ở x=207, gem bắt đầu ở x=292), nên vùng đọc rộng hơn là
    tràn sang pill bên cạnh: w=120 đọc ra '0 +' (dính nút mua), w=160 ra
    '0 3 +' và w=300 ra '+ 0 7 35' - ba con số khác nhau dính làm một, ra
    thành 735. w=80 đọc gọn từng pill một.
    """
    x1, y1, x2, y2 = element.bounds
    return readText((x1, y1, x2 + width, y2))


def digits(text):
    """Lọc lấy chữ số từ token số ĐẦU TIÊN, trả về None nếu không có.

    Không gộp mọi chữ số trong chuỗi: pill gem đọc ra '35 +' (dấu + của nút
    mua), và nếu sau này OCR bắt thêm thứ gì bên cạnh thì việc gộp sẽ tạo ra
    một con số bịa. Lấy token số đầu tiên thì thừa ra chỉ bị bỏ qua.
    """
    for token in (text or "").replace(",", "").replace(".", "").split():
        kept = "".join(c for c in token if c.isdigit())
        if kept:
            return int(kept)
    return None


def tap_home_tab():
    """Bấm tab Trang chủ, trừ khi paywall vừa bật lên che nó.

    Link "Chính Sách Bảo Mật" ở chân paywall nằm ĐÚNG chỗ tab Trang chủ. find()
    trên máy test tốn tới ~3s, nên toạ độ tab có thể lấy từ khung hình chụp
    trước khi paywall hiện: đo ở một lần chạy thật, cú bấm "về Home" rơi vào
    link đó và mở trình duyệt nổi đè lên game (xem close_floating_windows()).
    Nên kiểm tra lại paywall trên khung hình mới ngay trước khi bấm.
    """
    tab = find("tab-home", 0) or findText(HOME_TAB, 0)
    if not tab:
        return False
    shut = find("close-popup", 0)
    tap(shut or tab)
    return True


def dismiss_popups(rounds=3):
    """Đóng các popup chen ngang (ads, paywall) cho tới khi về màn hình game.

    Paywall "Gói cao cấp" bật lên sau khi bấm vào bài hát hoặc sau vài thao
    tác, và nó che TOÀN màn hình - mọi find() sau đó sẽ trượt vì thứ cần tìm
    nằm phía sau popup chứ không phải vì app hỏng. Gọi hàm này sau mỗi thao
    tác có thể sinh popup.
    """
    for _ in range(rounds):
        if isAdShowing():
            closeAd(required=False)
            continue
        shut = (
            find("event-close", 0, threshold=0.9)
            or find("close-popup", 0)
            or find("settings-close", 0)
        )
        if not shut:
            return
        tap(shut)
        wait(1_200)


def on_home():
    """Đang đứng ở Home và không có popup nào đè lên.

    Cần cả ba điều kiện. `star-hud` vẽ ở mọi tab nên một mình nó không nói gì;
    `settings-button` chỉ có ở Home. Nhưng popup event ("JP TRACK COMING") mở
    ra ngay trên Home mà vẫn chừa HUD và nút Setting ở phía trên - đo trên máy
    test, hai điều kiện đầu vẫn đúng, test coi như đã tới Home, rồi đếm
    songlist xuyên qua popup (thấy 2 bài) và đọc số HUD ra chuỗi rỗng.
    """
    return bool(
        find("star-hud", 0)
        and find("settings-button", 0)
        and not find("event-close", 0, threshold=0.9)
    )


def in_app():
    """App đang ở tiền cảnh hay đã bị thứ khác chiếm màn hình."""
    return app_id in (session().device.focused_activity() or "")


def close_floating_windows():
    """Tắt mọi app khác đang nổi thành cửa sổ freeform đè lên game.

    Trên máy test (MIUI), trang POLICY mở trình duyệt thành CỬA SỔ NỔI, và cửa
    sổ đó ở lại qua cả kill/mở lại game: game vẫn giữ focus nên in_app() báo
    True, trong khi trình duyệt che nửa trên màn hình - HUD, nút Setting. Đo ở
    lần chạy thật: test_home.py sót lại một cửa sổ như thế, back_to_home() bấm
    tab Trang chủ mãi mà on_home() không bao giờ đúng, và test_setting.py chạy
    sau đó fail từ bước mở Home. Focus không thấy nó, nên đọc danh sách task
    đang hiển thị.
    """
    out = session().device.shell("dumpsys", "window", "visible-apps") or ""
    closed = []
    for line in out.splitlines():
        if "mode=freeform" not in line or "visible=true" not in line:
            continue
        pkg = line.split(" A=", 1)[-1].split()[0].split(":", 1)[-1]
        if pkg and pkg != app_id and " A=" in line:
            session().device.shell("am", "force-stop", pkg)
            closed.append(pkg)
    if closed:
        print(f"close_floating_windows(): force-stopped {', '.join(closed)}")
        wait(1_000)
    return closed


def back_to_home():
    """Về Home từ bất kỳ tab/màn hình nào, và chờ HUD hiện lại.

    Không chỉ là "bấm tab Trang chủ". Sau section unlock-by-ads, màn hình đang
    ở có thể là:

    - App khác: đo trên máy test, đóng ad Pangle xong thì tiền cảnh nhảy sang
      com.xiaomi.mipicks (thẻ cài app của store). Bấm tab lúc này là bấm vào
      app khác, nên phải mở lại app trước.
    - Gameplay: xem hết video thì app mở luôn bài vừa unlock, mà trong gameplay
      không có thanh tab nào để bấm.
    - Home có popup che: nhãn "Trang chủ" nằm dưới cùng và bị paywall che kín,
      findText trả về None rồi tap() ném TestFailure - hỏng ở bước dọn dẹp chứ
      không phải ở bước test.

    Trả về True nếu về được Home, KHÔNG ném lỗi. Bản trước kết thúc bằng một
    waitUntil bắt buộc, và ở run 10 nó timeout rồi ném TestFailure - cả lần
    chạy dừng ở 30/38, mọi case phía sau không được chạy. Về Home là bước dọn
    dẹp; dọn hỏng thì case kế tiếp tự fail đúng chỗ của nó, hoặc bên gọi tự
    alert() trên giá trị trả về. "Ở Home" là on_home(), không chỉ `star-hud`.
    """
    close_floating_windows()
    if not in_app():
        open_app(app_id)
        wait(3_000)
    dismiss_popups()
    # Trong gameplay thì thoát bằng nút close của màn chơi, không có tab.
    for _ in range(3):
        close_floating_windows()
        if on_home():
            break
        quit_play = find("btnAutoplayClose", 0)
        if quit_play:
            tap(quit_play)
            wait(2_000)
            dismiss_popups()
            continue
        if tap_home_tab():
            wait(1_500)
            # Bấm tab khi đã ở Home không cuộn danh sách về đầu, nên header
            # có thể vẫn nằm ngoài màn hình.
            for _ in range(8):
                if on_home():
                    break
                scrollVerticle(60)
                wait(600)
            continue
        # Hết đường đi bằng UI thì khởi động lại. Nặng tay, nhưng mọi chỗ gọi
        # hàm này đều nằm sau phần so sánh gem/star sau khi kill app, nên
        # restart không làm hỏng dữ liệu của case nào còn lại.
        kill(app_id)
        open_app(app_id)
        reach_home()
    return bool(waitUntil(
        on_home,
        timeout=10_000, label="home HUD", required=False,
    ))


def reach_home(timeout=60_000, settle=6_000):
    """Mở app và chờ tới khi Home thực sự hiện ra, dọn hết popup chen ngang.

    Không dùng thẳng `waitUntil(find("star-hud"))`: sau khi mở app, thứ hiện
    ra trước có thể là ad, có thể là paywall "Gói cao cấp" - và paywall che
    kín Home. Nếu chạy tiếp lúc đó thì MỌI assertion của Header đều trượt,
    không phải vì app thiếu button mà vì đang đo nhầm màn hình.

    Thấy Home MỘT LẦN là chưa đủ, nên sau khi thấy còn phải giữ thêm `settle`
    nữa mới tính. Đo trên máy test: Home vẽ xong ở giây thứ 6, paywall mới bật
    lên ở giây 7.5 - tức là vòng lặp cũ đã kịp báo "tới Home rồi" trước khi
    popup xuất hiện, và toàn bộ Header sau đó đo phía sau popup. Hễ trong thời
    gian giữ mà có thứ gì chen lên thì quay lại dọn tiếp.

    Trả về True nếu tới được Home và Home đứng yên.
    """
    # Đếm bằng đồng hồ thật, không trừ dần theo `wait()`. Mỗi vòng lặp còn tốn
    # thêm 4 lần find (~11s trên máy test) mà bản trước không tính vào deadline,
    # nên "timeout 60s" chạy thật tới ~390s: test treo rất lâu ở một màn hình
    # đã hỏng thay vì bỏ cuộc và để các case sau chạy tiếp.
    deadline = time.monotonic() + timeout / 1000.0
    while time.monotonic() < deadline:
        close_floating_windows()
        # App phải đang ở tiền cảnh TRƯỚC khi bấm bất cứ thứ gì. Ngay sau
        # `kill()` thì app chưa vẽ xong (tiền cảnh đọc ra 'unknown'), mà vòng
        # lặp vẫn tìm chữ trên khung hình cũ còn sót lại rồi bấm: đo được ở
        # run 10, nó bấm 'TRANG CHU' và mở ra Chrome (ChromeTabbedActivity).
        # Từ đó mọi find đều đo trên trình duyệt chứ không phải trên game.
        if not in_app():
            open_app(app_id)
            wait(3_000)
            continue
        if on_home():
            held = 0
            while held < settle:
                wait(1_500)
                held += 1_500
                if not on_home():
                    break  # có thứ chen lên - quay lại vòng dọn popup
            else:
                return True
            continue
        if isAdShowing():
            closeAd(required=False)
        else:
            # `open_app` không đưa app về Home nếu app đang chạy sẵn: nó chỉ
            # mang app lên tiền cảnh, ở nguyên màn hình lần trước bỏ dở. Một
            # lần chạy hỏng giữa chừng ở màn Setting là lần chạy sau mở lên
            # thấy Setting, và `star-hud` không bao giờ xuất hiện. Nên phải
            # đóng cả màn Setting lẫn panel con, không chỉ popup.
            shut = (
                find("event-close", 0, threshold=0.9)
                or find("close-popup", 0)
                or find("panel-close", 0, threshold=0.88)
                or find("panel-ok", 0)
                or find("settings-close", 0)
            )
            if shut:
                tap(shut)
            else:
                # Không có gì để đóng mà vẫn chưa thấy Home: app đang ở một TAB
                # khác. Lần chạy trước kết thúc ở tab Bóng thì lần này mở lên
                # vẫn là tab Bóng - `star-hud` có (HUD hiện ở mọi tab) nhưng
                # `settings-button` thì không, nên vòng lặp không bao giờ đủ
                # điều kiện và cháy hết 60s. Không có popup nào để đóng cả;
                # đường ra là bấm tab Trang chủ.
                # `tab-home`, KHÔNG phải `home-tab`: cái sau là nhãn "HOME"
                # tiếng Anh cắt lúc tab đang được chọn, nên thứ nó khớp là cái
                # thẻ sáng của tab đang chọn chứ không phải icon ngôi nhà -
                # đứng ở tab Bóng nó khớp 0.99 ngay trên tab Bóng, và cú bấm
                # "về Home" chỉ chọn lại đúng tab đang đứng.
                tap_home_tab()
        wait(2_000)
    return on_home()


def start():
    """Mở app và vào Home. Mỗi file test gọi hàm này đầu tiên.

    Mỗi file phải tự đứng được một mình: runner chạy chúng thành các process
    riêng, theo thứ tự không đảm bảo, và chạy lẻ một file cũng phải ra kết quả
    đúng - nên không file nào được giả định file trước đã để app ở Home.
    """
    open_app(app_id)
    alert(reach_home(), name="Mở app và vào được màn hình Home")


# ---------------------------------------------------------------------------
# Setting
# ---------------------------------------------------------------------------

def open_setting():
    """Đảm bảo màn hình Setting đang mở, sạch, không có panel con nào đè lên.

    Không coi "thấy `settings-close`" là đủ: nút đó vẫn thấy khi có panel con
    đè lên, và HOW TO PLAY dùng đúng nút X đó cho màn của nó.
    """
    if find("settings-close", 0) and close_sub_panel():
        return True
    button = find("settings-button", 0)
    if not button:
        back_to_home()
        button = find("settings-button", 0)
    if not button:
        return False
    tap(button)
    return bool(waitUntil(
        lambda: find("settings-close", 0), timeout=10_000,
        label="Setting", required=False,
    ))


def close_sub_panel():
    """Đóng màn hình con vừa mở trong Setting.

    Panel con KHÔNG đóng bằng `settings-close`: đo trên máy test, sau khi mở
    GAME SETTINGS rồi bấm `settings-close` thì cái đóng đi là màn hình Setting
    bên ngoài, còn panel con vẫn nằm đè lên. Màn hình sau đó là một mớ hai lớp
    chồng nhau, và dòng HOW TO PLAY tìm không ra vì bị panel con che.

    Chỉ đóng bằng TEMPLATE, tuyệt đối không tìm nút xác nhận bằng chữ. Bản
    trước dùng findText(["Đồng ý", "OK", "Xong", "Done"]) và nó đã bấm nhầm
    vào ô "Indonesia" trong danh sách ngôn ngữ - findText khớp cả chuỗi con
    sau khi bỏ dấu, mà "indonesia" thì chứa "done". Hậu quả là app đổi sang
    tiếng Indonesia giữa chừng và mọi nhãn tiếng Việt sau đó tìm không ra.
    Trong một màn hình đầy nhãn do người dùng chọn, tên nút là thứ không được
    phép đoán.

    Mỗi màn con đóng một kiểu, đo trên máy test:

    - LANGUAGE: nút X lục giác xám ở chân panel (`panel-close`).
    - GAME SETTINGS: không có X, chỉ có nút hồng "Đồng ý" (`panel-ok`). Bản
      trước không biết nút này, không tìm thấy gì để bấm và coi như xong.
    - HOW TO PLAY: không phải panel mà là một màn riêng, đóng bằng nút X ở
      góc - trùng hình với `settings-close`. Phân biệt bằng tiêu đề: đứng ở
      màn này thì không thấy tiêu đề "Cấu hình".

    Trả về True nếu đang đứng ở màn Setting và không còn gì đè lên. Không
    chứng minh bằng "đọc được dòng Setting": panel con chỉ làm tối màn Setting
    chứ không che kín, OCR vẫn đọc được "CỬA HÀNG" bên dưới panel ngôn ngữ.
    Bằng chứng đúng là tiêu đề còn đó VÀ không còn nút đóng panel nào. Đo ở
    run 10: hàm cũ trả về im lặng trong khi panel vẫn nằm đè, và ba case sau
    (HOW TO PLAY, RATE US, POLICY) fail với "không tìm thấy dòng để bấm" -
    đọc log thì tưởng app thiếu dòng, thật ra là bước dọn dẹp chưa xong.
    """
    def panel_closer():
        return (
            find("panel-close", 0, threshold=0.88)
            or find("panel-ok", 0)
            or find("close-popup", 0)
        )

    for _ in range(3):
        shut = panel_closer()
        if not shut and find("settings-close", 0) and not findText(SETTING_TITLE, 0):
            shut = find("settings-close", 0)  # màn con toàn màn hình (HOW TO PLAY)
        if not shut:
            break
        tap(shut)
        wait(1_200)
    return bool(
        find("settings-close", 0)
        and findText(SETTING_TITLE, 0)
        and not panel_closer()
    )


def setting_row(label, needles, expect, timeout=6_000):
    """Bấm một dòng trong Setting rồi kiểm tra màn hình con mở đúng."""
    if not open_setting():
        alert(False, name=f"Setting - {label}: không mở được màn hình Setting")
        return
    row = findText(needles, 0)
    if not row:
        alert(False, name=f"Setting - {label}: không tìm thấy dòng để bấm")
        return
    tap(row)
    # Chờ có điều kiện chứ không chờ cứng: panel con trượt vào mất một nhịp, và
    # ở run 10 lần đọc sau 2s rơi đúng lúc panel ngôn ngữ chưa vẽ xong.
    alert(
        waitUntil(lambda: findText(expect, 0), timeout=timeout,
                  label=f"Setting - {label}", required=False),
        name=f"Setting - {label}",
    )
    # Panel không đóng được thì báo ngay ở ĐÂY, dưới đúng tên dòng vừa mở.
    # Để im thì lỗi hiện ra ở dòng kế tiếp dưới dạng "không tìm thấy dòng để
    # bấm", và người đọc log đi tìm lỗi ở nhầm chỗ. Dòng kế tiếp vẫn tự cứu
    # được: open_setting() về Home rồi mở lại Setting từ đầu.
    if not close_sub_panel():
        alert(False, name=f"Setting - {label}: đóng panel con, quay lại Setting")


def leaves_app(label, needles, extra=()):
    """Bấm một dòng rời khỏi app, kiểm tra app nào nhận, rồi quay lại game."""
    if not open_setting():
        alert(False, name=f"Setting - {label}: không mở được màn hình Setting")
        return
    row = findText(needles, 0)
    if not row:
        alert(False, name=f"Setting - {label}: không tìm thấy dòng để bấm")
        return
    tap(row)
    # Chờ tới khi app khác nhận focus, không đọc một lần sau một khoảng cứng:
    # thời gian store/trình duyệt mở lên không cố định. Đo trên máy test, cùng
    # một cú bấm RATE US có lần Play Store lên sau 1s, có lần quá 3.5s và lần
    # đọc duy nhất vẫn thấy game - case fail dù app làm đúng.
    waitUntil(lambda: not in_app(), timeout=10_000,
              label=f"{label}: app khác nhận focus", required=False)
    wait(1_000)
    focus = session().device.focused_activity() or ""
    left = app_id not in focus
    alert(
        left or (bool(findText(list(extra), 0)) if extra else False),
        name=f"Setting - {label} ({focus.split('/')[0] or 'n/a'})",
    )
    # Quay lại game. Back ở đây là thao tác của người dùng trên app khác, không
    # phải cách đóng ad, nên dùng được.
    if left:
        session().device.shell("input", "keyevent", "4")
        wait(2_500)
        # Back không phải lúc nào cũng đóng được app kia. Trên máy test (MIUI)
        # trình duyệt mở thành CỬA SỔ NỔI đè lên game, và sau Back nó vẫn nằm
        # đó trong khi game đã lấy lại focus: in_app() báo True, còn mọi find()
        # của lần chạy sau đo trên khung hình có trình duyệt che nửa màn. Nên
        # không hỏi lại focus mà đóng thẳng đúng package đã nhận cú bấm - app
        # đó do chính test mở ra, nên test dọn nó. Trừ khi focus rỗng hoặc là
        # launcher: tắt launcher là tắt màn hình chính của máy.
        other = focus.split("/")[0]
        if other and "launcher" not in focus.lower() and "home" not in other:
            session().device.shell("am", "force-stop", other)
            wait(1_000)
        if not in_app():
            open_app(app_id)
            wait(3_000)
    if not close_sub_panel():
        alert(False, name=f"Setting - {label}: quay lại màn Setting")


# ---------------------------------------------------------------------------
# Shop Ball
# ---------------------------------------------------------------------------

def open_ball_tab():
    """Mở tab Bóng và chờ lưới ball vẽ xong.

    Bấm một lần rồi chờ là không đủ. Đo trên máy test: sau section Setting,
    paywall "Gói cao cấp" thường đang che kín màn hình, nên cú bấm đầu tiên
    rơi vào popup chứ không vào thanh tab - run 5 đo được `tab-ball` khớp
    0.99 rồi ngay sau đó `ball-equipped` không thấy gì trong 15s, vì cái
    được bấm là popup. Nên mỗi vòng phải dọn popup TRƯỚC khi bấm tab.

    Ưu tiên template hơn findText: `tab-ball` khớp 0.99, còn findText bỏ dấu
    rồi so chuỗi con nên "bong" là một cái needle ngắn dễ dính vào nhãn khác
    trên màn hình.
    """
    for _ in range(3):
        if find("ball-equipped", 0):
            return True
        dismiss_popups()
        tab = find("tab-ball", 0) or findText(BALL_TAB, 0)
        if not tab:
            back_to_home()
            continue
        tap(tab)
        if waitUntil(
            lambda: find("ball-equipped", 0), timeout=12_000,
            label="màn hình Shop Ball", required=False,
        ):
            return True
    return bool(find("ball-equipped", 0))
