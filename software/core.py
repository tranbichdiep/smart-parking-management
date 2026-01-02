import os
import sqlite3
import calendar
import shutil
import cv2
from datetime import datetime

# --- Cấu hình chung ---
SECRET_KEY = 'day_la_mot_chuoi_bi_mat_rat_dai_va_kho_doan'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, '..', 'database', 'parking.db')
SNAPSHOT_DIR = os.path.join(BASE_DIR, 'static', 'snapshots')
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

# *** MỚI: Token bí mật cho các thiết bị ESP32 ***
DEVICE_SECRET_TOKEN = "my_secret_device_token_12345"

# *** MỚI: Cấu hình 2 Camera RTSP ***
# Lưu ý: Thay đổi URL này phù hợp với camera thực tế của bạn
RTSP_URL_IN = "rtsp://admin:admin@192.168.0.101:8554/live"
RTSP_URL_OUT = "rtsp://admin:admin@192.168.0.103:8554/live"


def register_filters(app):
    @app.template_filter('vn_dt')
    def vn_dt(value, fmt="%d/%m/%Y %H:%M:%S"):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime(fmt)
        except Exception:
            return value


# --- Hàm hỗ trợ ---
def get_db_connection():
    # SỬA LỖI "database is locked"
    conn = sqlite3.connect(DATABASE, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn


def escape_like(value: str) -> str:
    """Escapes wildcard chars for safe LIKE queries."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def parse_int_param(raw_value, default, max_value=None):
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    if value < 1:
        value = default
    if max_value is not None:
        value = min(value, max_value)
    return value


def add_months(base_date, months):
    """Cộng thêm số tháng, giữ nguyên ngày trong tháng nếu có thể."""
    month = base_date.month - 1 + months
    year = base_date.year + month // 12
    month = month % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return base_date.replace(year=year, month=month, day=day)


def generate_next_employee_code(conn):
    """Sinh mã nhân viên 6 số (001234) dựa trên mã lớn nhất hiện có."""
    cursor = conn.execute(
        "SELECT MAX(CAST(employee_code AS INTEGER)) FROM users WHERE employee_code GLOB '[0-9][0-9]*'"
    )
    max_code = cursor.fetchone()[0] or 0
    next_code_val = int(max_code) + 1
    if next_code_val > 999999:
        raise ValueError("Đã hết dải mã nhân viên (tối đa 999999).")
    return f"{next_code_val:06d}"


# --- HÀM CHỤP ẢNH ĐƯỢC CẬP NHẬT ĐỂ DÙNG 2 CAMERA ---
# def capture_snapshot(card_id, event_type):
#     """
#     Kết nối đến RTSP, chụp một khung hình và lưu lại.
#     Trả về tên file nếu thành công, hoặc tên file placeholder nếu thất bại.
#     """
#     placeholder_filename = "placeholder.jpg" # Tên file dự phòng
#     
#     # === THAY ĐỔI: Chọn đúng URL camera ===
#     if event_type == 'in':
#         rtsp_url = RTSP_URL_IN
#         print(f"Chụp ảnh VÀO từ: {rtsp_url}")
#     elif event_type == 'out':
#         rtsp_url = RTSP_URL_OUT
#         print(f"Chụp ảnh RA từ: {rtsp_url}")
#     else:
#         rtsp_url = RTSP_URL_IN # Mặc định
#     # ======================================
#     
#     cap = None
#     try:
#         # 1. Kết nối đến camera
#         cap = cv2.VideoCapture(rtsp_url)
#         
#         # Thử đọc 5 khung hình đầu để xóa bộ đệm (buffer)
#         for _ in range(5):
#             cap.read()
#             
#         ret, frame = cap.read() # Đọc khung hình chính
#         
#         if not ret or frame is None:
#             print(f"Lỗi: Không thể đọc frame từ camera RTSP: {rtsp_url}")
#             raise Exception("Không thể đọc frame")
#
#         # 2. Tạo tên file và đường dẫn
#         timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
#         filename = f"{card_id}_{timestamp}_{event_type}.jpg"
#         destination_path = os.path.join(SNAPSHOT_DIR, filename)
#
#         # 3. Lưu ảnh
#         cv2.imwrite(destination_path, frame)
#         print(f"Đã lưu ảnh chụp: {filename}")
#         return filename
#
#     except Exception as e:
#         print(f"Lỗi khi chụp ảnh từ {rtsp_url}: {e}. Sử dụng ảnh placeholder.")
#         # Nếu có lỗi, copy ảnh placeholder
#         placeholder_path_src = os.path.join(BASE_DIR, 'static', placeholder_filename)
#         if not os.path.exists(placeholder_path_src):
#             try:
#                 # Tạo placeholder nếu chưa có
#                 img = cv2.vconcat([cv2.vconcat([cv2.Mat(100, 300, cv2.CV_8UC3, (128, 128, 128))])])
#                 cv2.putText(img, 'CAMERA OFFLINE', (50, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
#                 cv2.imwrite(placeholder_path_src, img)
#             except: pass # Bỏ qua nếu không tạo được
#         
#         # Copy file placeholder đến đúng vị trí
#         timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
#         filename = f"{card_id}_{timestamp}_{event_type}_offline.jpg"
#         destination_path = os.path.join(SNAPSHOT_DIR, filename)
#         try:
#             shutil.copy(placeholder_path_src, destination_path)
#         except:
#              return placeholder_filename # Trả về placeholder gốc
#         return filename # Trả về file placeholder đã copy
#
#     finally:
#         # 4. Luôn giải phóng camera
#         if cap:
#             cap.release()


def capture_snapshot(card_id, event_type):
    """
    PHIÊN BẢN TEST PHẦN CỨNG:
    Hàm này bỏ qua việc kết nối Camera RTSP để tránh bị Lag/Timeout.
    Nó sẽ copy ảnh placeholder.jpg có sẵn thành ảnh chụp mới.
    """
    print(f"--- [TEST MODE] Bỏ qua Camera, tạo ảnh giả lập cho thẻ {card_id} ---")
    
    placeholder_filename = "placeholder.jpg"
    
    # Tạo tên file mới dựa trên thời gian
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{card_id}_{timestamp}_{event_type}_offline.jpg"
    
    # Đường dẫn nguồn (ảnh mẫu) và đích (ảnh lưu)
    placeholder_path_src = os.path.join(BASE_DIR, 'static', placeholder_filename)
    destination_path = os.path.join(SNAPSHOT_DIR, filename)
    
    try:
        # Kiểm tra nếu chưa có ảnh mẫu thì tạo ra một cái (phòng hờ)
        if not os.path.exists(placeholder_path_src):
            try:
                # Tạo ảnh màu xám đơn giản bằng OpenCV
                img = cv2.Mat(100, 300, cv2.CV_8UC3, (128, 128, 128))
                cv2.putText(img, 'NO CAMERA', (50, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.imwrite(placeholder_path_src, img)
            except: 
                pass # Bỏ qua nếu không cài opencv hoặc lỗi tạo ảnh
            
        # Copy ảnh mẫu sang thư mục snapshots
        shutil.copy(placeholder_path_src, destination_path)
        return filename
        
    except Exception as e:
        print(f"Lỗi khi tạo ảnh giả lập: {e}")
        return placeholder_filename # Trả về ảnh gốc nếu lỗi
