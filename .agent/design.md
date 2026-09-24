# Android Auto test SDK:
* script language: Python
* connect device through ADB
* cung cấp khả năng viết testcase bằng Python script
* SDK được viết dưới dạng command line application
* user run trực tiếp testcase script bằng python

## API methods: các method cung cấp cho người dùng khi viết testcase
* alert(expression): kiểm tra điều kiện pass/fail của testcase và in kết quả ra màn hình, gồm tên testcase (filename) và test result status
* clear(app_id): xóa bộ nhớ storage của app
* open(app_id): mở app (sử dụng app id)
* hide(app_id): ẩn app xuống background, tương đương bấm button home
* kill(app_id): kill running app, force stop
* tap(element) return position: chạm vào element trên màn hình
* doubleTap(element) return position: double tap ở vị trí của element
* readText(element) return string: đọc text OCR từ 1 element UI trên màn hình 
* find(image-pattern) return list<element>: tìm các element trên màn hình sử dụng pattern matching, nếu ko tìm thấy, trả về null
* findText(string) return element chứa text cần tìm: tìm xem có xuất hiện text cần tìm trên màn hình hay không, không xét kí tự hoa/thường
* find(images[]) return bool: tìm xem trên màn hình có xuất hiện ít nhất 1 element trong list param hay k
* waitUntil(lambda_expression, timeout: ms): chờ tới khi expression trả về 1/true/non-null, nếu sau thời gian timeout vẫn chưa success thì đánh dấu testcase là failed và dừng auto-play
* scrollVerticle(percent_of_screen_height): cuộn màn hình xuống dọc 1 đoạn màn hình (theo số phần trăm chiều cao màn hình, chẳng hạn scrollVerticle(-20) nghĩa là cuộn xuống 20% height) 
* scrollHorizontal(percent_of_screen_width): cuộn màn hình sang phải 1 đoạn màn hình (theo số phần trăm chiều rộng màn hình, chẳng hạn scrollHorizontal(-20) nghĩa là cuộn sang trái 20% width)

* mỗi API method cần in ra console tóm tắt hành động của method để user nắm được các bước thực thi

# Implement

## task 1
* viết module 'auto-play' sử dụng opencv và adb: đọc stream màn hình sử dụng scrcpy, dùng opencv để pattern matching với UI element database (đọc từ script element-database.py) với cấu trúc kiểu dictionary trong đó key là ID của element, value là relative path dẫn tới file ảnh nhận diện element đó

* mỗi testcase giờ là một python script độc lập, import module auto-play

* từ sample test script (pseudo code) này viết cho tôi 1 testcase script:
> app_id = com.amanotes.beathopper
> stop(app_id)
> clear(app_id)
> open(app_id)
>
> waitUntil(() => find("welcome-screen") || findText("notifications?")) // chờ tới khi tìm thấy UI element "welcome-screen" trên màn hình
>
> if(findText("notifications?"))
>   tap(findText("ALLOW"))
>
> waitUntil(() => findText("POP))
> wait 100ms
> tap(findText("POP"))
> wait 100ms
> tap(findText("Continue"))
> wait 100ms
>
> do 
>   skip = findText("Prefer not to say")
>   if(skip):
>       tap(skip)
>       wait 100ms
> while(skip != null)
> var chooseTutSongScreen = findText("Let's play your first song")
>
> alert(chooseTutSongScreen)
>
> if(chooseTutSongScreen)
>   var listPlayButtons = find("play-button")
>   alert(() => listPlayButtons.Length >= 4)

# task 2
* một số step trong testcase có thể k nhất thiết phải xuất hiện, vậy nên trong waitUntil cần thêm tùy chọn bool, quyết định xem waitUntil này có bắt buộc phải có k

# task 3: optimize latency
* nén ảnh/giảm độ phân giải stream màn hình về kích thước tối ưu
* giảm buffer màn hình về 0 có cải thiện latency k, nếu có hãy thực hiện
* chọn video encoder tối ưu nhất
* cần đo thời gian từ khi chạy lệnh lấy frame màn hình tới khi gọi lệnh thao tác với thiết bị cho mỗi bước

# task 4
* mặc định nếu không tìm thấy text/element thì tự động thử lại tối đa 3 lần (thêm param số lần thử lại), mỗi lần cách nhau 100ms. sửa vào API method

# task 5
* thêm overload của findText: truyền vào một mảng string để tìm kiếm. Trả về element chứa text đầu tiên trong mảng mà có xuất hiện trên màn hình

# task 6
* viết script python test-runner, chạy tất cả testcase trong 1 folder, trả về kết quả dạng table, xuất ra report html

# task 7
* trong element-database, mở rộng để một element có thể có nhiều variant, ví dụ cùng một nút close x nhưng có thể có nhiều hình dạng, kiểu dáng khác nhau.

# task 8
* bổ sung API method:
    * findLayout(image-pattern), tương tự hàm find nhưng sử dụng phương pháp edge template matching thay vì template matching
    * multi-tap(element, vector2 offset, số lần tap, duration)
    * multi-tap(normalized-position, số lần tap, duration). normalized-position lấy góc top-left màn hình làm gốc tọa độ, trục x hướng sang phải, trục y hướng xuống bottom
    * tap(normalized-position) và doubleTab(normalized-position)

# task 9
* generate các testcase script để thực hiện automation testing cho các testcase trong sheet sau: https://docs.google.com/spreadsheets/d/1THhmMRK9_1eRU72-iPB00-VgJDHPw1nDS-eq2KCCSIg/edit?usp=sharing