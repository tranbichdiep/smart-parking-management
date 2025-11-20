import sqlite3
import os
import random
from datetime import datetime, timedelta

# --- CẤU HÌNH ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, '..', 'database', 'parking.db')

# Giá vé giả lập (10.000đ/giờ)
FEE_PER_HOUR = 10000 

def create_fake_data():
    print(f"Đang kết nối đến database: {DATABASE}")
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Xóa dữ liệu cũ (Tùy chọn - Nếu muốn xóa sạch làm lại từ đầu thì bỏ comment dòng dưới)
    # cursor.execute("DELETE FROM transactions")
    
    print("Đang sinh dữ liệu giả cho 30 ngày qua...")

    # Danh sách biển số xe mẫu
    plates = ["29A-123.45", "30E-999.99", "29H-567.89", "14A-111.22", "90B-333.44", "29D-654.32", "18A-888.88"]
    
    total_records = 0
    
    # Lặp qua 30 ngày gần nhất
    for i in range(30, -1, -1):
        current_date = datetime.now() - timedelta(days=i)
        date_str = current_date.strftime("%Y-%m-%d")
        
        # Mỗi ngày sinh ngẫu nhiên từ 10 đến 40 xe
        daily_cars = random.randint(10, 40)
        
        # Nếu là cuối tuần (T7, CN) thì cho đông khách hơn xíu
        if current_date.weekday() >= 5: 
            daily_cars += 15

        for _ in range(daily_cars):
            # 1. Random giờ vào (từ 7h sáng đến 20h tối)
            hour_in = random.randint(7, 20)
            minute_in = random.randint(0, 59)
            entry_time = current_date.replace(hour=hour_in, minute=minute_in, second=0)
            
            # 2. Random thời gian gửi (từ 30 phút đến 5 tiếng)
            duration_minutes = random.randint(30, 300)
            exit_time = entry_time + timedelta(minutes=duration_minutes)
            
            # 3. Tính phí
            hours_parked = max(1, -(-duration_minutes // 60)) # Làm tròn lên
            fee = hours_parked * FEE_PER_HOUR
            
            # 4. Random biển số và ID thẻ
            plate = random.choice(plates)
            card_id = f"FAKE_{random.randint(1000, 9999)}"
            
            # 5. Chèn vào DB
            cursor.execute("""
                INSERT INTO transactions 
                (card_id, license_plate, entry_time, exit_time, fee, entry_snapshot, exit_snapshot, security_user)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                card_id,
                plate,
                entry_time.strftime("%Y-%m-%d %H:%M:%S"),
                exit_time.strftime("%Y-%m-%d %H:%M:%S"),
                fee,
                "placeholder.jpg", # Ảnh giả
                "placeholder.jpg", # Ảnh giả
                "admin_seed"
            ))
            total_records += 1
            
    conn.commit()
    conn.close()
    print(f"--- HOÀN TẤT! Đã thêm {total_records} giao dịch giả. ---")
    print("Hãy quay lại trang Thống kê để xem biểu đồ.")

if __name__ == '__main__':
    create_fake_data()