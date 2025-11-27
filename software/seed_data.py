import sqlite3
import os
import random
from datetime import datetime, timedelta

# --- CẤU HÌNH ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, '..', 'database', 'parking.db')

def get_current_fee(cursor):
    """Hàm lấy giá vé hiện tại từ cấu hình Database"""
    try:
        cursor.execute("SELECT value FROM settings WHERE key='fee_per_hour'")
        result = cursor.fetchone()
        if result:
            return int(result[0])
        return 10000 # Giá mặc định nếu chưa cài đặt
    except:
        return 10000

def create_fake_data():
    print(f"Đang kết nối đến database: {DATABASE}")
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # --- SỬA ĐỔI: Lấy giá tiền động từ Database ---
    current_fee = get_current_fee(cursor)
    print(f"Đang sử dụng mức phí từ cài đặt: {current_fee:,.0f} VNĐ/giờ")
    # ---------------------------------------------

    # Xóa dữ liệu cũ (Tùy chọn)
    # cursor.execute("DELETE FROM transactions")
    
    print("Đang sinh dữ liệu giả cho 30 ngày qua...")

    plates = ["29A-123.45", "30E-999.99", "29H-567.89", "14A-111.22", "90B-333.44", "29D-654.32", "18A-888.88"]
    total_records = 0
    
    for i in range(30, -1, -1):
        current_date = datetime.now() - timedelta(days=i)
        
        daily_cars = random.randint(10, 40)
        if current_date.weekday() >= 5: 
            daily_cars += 15

        for _ in range(daily_cars):
            # 1. Random giờ
            hour_in = random.randint(7, 20)
            minute_in = random.randint(0, 59)
            entry_time = current_date.replace(hour=hour_in, minute=minute_in, second=0)
            
            # 2. Random thời gian gửi
            duration_minutes = random.randint(30, 300)
            exit_time = entry_time + timedelta(minutes=duration_minutes)
            
            # 3. Tính phí (SỬ DỤNG GIÁ ĐỘNG)
            hours_parked = max(1, -(-duration_minutes // 60)) 
            fee = hours_parked * current_fee  # <--- Dùng biến current_fee
            
            plate = random.choice(plates)
            card_id = f"FAKE_{random.randint(1000, 9999)}"
            
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
                "placeholder.jpg",
                "placeholder.jpg",
                "admin_seed"
            ))
            total_records += 1
            
    conn.commit()
    conn.close()
    print(f"--- HOÀN TẤT! Đã thêm {total_records} giao dịch giả với giá {current_fee:,.0f}đ/h. ---")

if __name__ == '__main__':
    create_fake_data()