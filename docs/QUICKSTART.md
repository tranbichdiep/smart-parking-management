# Quickstart

Các bước tối thiểu để chạy web app Smart Parking trên máy cá nhân.

## 1) Chuẩn bị
- Python 3.10+ và `pip`.
- Ubuntu/debian cần thư viện cho OpenCV: `sudo apt-get install python3-venv libgl1 libglib2.0-0`.
- Cổng 5000 trống; camera RTSP có thể bỏ qua bằng `CAMERA_TEST_MODE=true`.

## 2) Thiết lập môi trường
```bash
cd smart-parking-management
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r software/requirements.txt
```

## 3) Cấu hình
- Sao chép và chỉnh sửa `software/.env` nếu cần:
  - `DATABASE_PATH=database/parking.db` (đường dẫn DB; mặc định file đã có sẵn trong repo).
  - `DEVICE_SECRET_TOKEN`, `RTSP_URL_IN`, `RTSP_URL_OUT` khớp với thiết bị/camera thực tế.
  - Đặt `CAMERA_TEST_MODE=true` để bỏ qua camera và dùng ảnh placeholder khi demo.

## 4) Khởi tạo dữ liệu (tuỳ chọn nếu muốn DB sạch)
```bash
python software/setup_db.py    # Tạo bảng + tài khoản admin/baove (pass 123456)
python software/seed_data.py   # Sinh giao dịch giả lập để xem báo cáo
```

## 5) Chạy ứng dụng web
```bash
python software/run.py
# Mặc định http://localhost:5000
```

Đăng nhập:
- Admin: `admin` / `123456`
- Bảo vệ: `baove` / `123456`

## 6) Kết nối thiết bị ESP32 (tuỳ chọn)
- Nạp `hardware/main/main.ino`.
- Vào portal WiFiManager của ESP32 để cấu hình IP/port server, token (`DEVICE_SECRET_TOKEN`), và WiFi.
- Thiết bị gọi `/api/gate/device_scan` và polling `/api/gate/check_action_status`.

## 7) Công cụ hỗ trợ
- Thống kê mã nguồn: `python check.py` (ghi `project_stats.json`).
- Ảnh lưu ở `software/static/snapshots`; database ở `software/database/parking.db`.
