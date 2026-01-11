# Smart Parking Management

Tài liệu giới thiệu nhanh về đồ án quản lý bãi đỗ xe thông minh: web app quản trị (Flask + SQLite) kết hợp phần cứng ESP32 đọc RFID/điều khiển servo, kèm camera giám sát vào/ra.

## Thành phần
- `software/`: Ứng dụng Flask (quản trị, bảo vệ, API cho thiết bị), giao diện HTML/CSS, snapshot camera, database SQLite.
- `hardware/main/main.ino`: Firmware ESP32 (WiFiManager cấu hình IP server, gọi API vào/ra, điều khiển RFID + servo + cảm biến).
- `check.py`: Script thống kê LOC/size/artifact của toàn bộ repo (lưu `project_stats.json`).
- `software/database/parking.db`: File SQLite mặc định (có tài khoản mẫu).

## Luồng hoạt động
1) ESP32 quẹt thẻ RFID → gửi `/api/gate/device_scan` kèm `DEVICE_SECRET_TOKEN`.
2) Backend ghi `pending_actions` và hiển thị cho bảo vệ xác nhận vào/ra (giao diện security dashboard).
3) Khi xác nhận, backend cập nhật `transactions`, điều khiển servo qua thiết bị (polling) và lưu snapshot từ camera (RTSP hoặc chế độ test).
4) Quản trị viên quản lý thẻ, nhân viên, giá vé, báo cáo giao dịch trên giao diện admin.

## Cấu hình chính (file `software/.env`)
- `DATABASE_PATH`: Đường dẫn DB (mặc định `database/parking.db`).
- `SNAPSHOT_DIR`: Nơi lưu ảnh chụp camera.
- `DEVICE_SECRET_TOKEN`: Token ESP32 dùng khi gọi API.
- `RTSP_URL_IN` / `RTSP_URL_OUT`: RTSP camera vào/ra. Đặt `CAMERA_TEST_MODE=true` để bỏ qua camera và dùng ảnh placeholder.
- `SECRET_KEY`, `SQLITE_TIMEOUT`: Bảo mật session và timeout SQLite.

## Tài khoản mẫu (khi khởi tạo DB với `setup_db.py`)
- Admin: `admin` / `123456`
- Bảo vệ: `baove` / `123456`

## Lệnh thường dùng
- Khởi tạo/chuẩn hoá DB: `python software/setup_db.py`
- Sinh dữ liệu demo giao dịch: `python software/seed_data.py`
- Chạy web app: `python software/run.py` (truy cập http://localhost:5000)
- Thống kê mã nguồn: `python check.py`
