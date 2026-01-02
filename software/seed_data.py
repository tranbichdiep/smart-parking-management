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

def get_monthly_fee(cursor):
    """Lấy phí vé tháng hiện tại từ bảng settings."""
    try:
        cursor.execute("SELECT value FROM settings WHERE key='monthly_fee'")
        result = cursor.fetchone()
        if result:
            return int(result[0])
        return 1200000
    except:
        return 1200000

def seed_monthly_payments(cursor, monthly_fee, month_count=8):
    """Sinh dữ liệu giả lập đóng tiền vé tháng cho nhiều tháng gần đây."""
    print(f"Đang sinh dữ liệu đóng tiền vé tháng {month_count} tháng gần nhất...")
    monthly_cards = [
        ("MONTH_1001", "Nguyễn Văn A", "30A-555.88"),
        ("MONTH_1002", "Trần Thị B", "29B-111.22"),
        ("MONTH_1003", "Phạm Văn C", "90F-333.44"),
    ]

    for card_id, holder, plate in monthly_cards:
        cursor.execute(
            """
            INSERT OR IGNORE INTO cards (card_id, holder_name, license_plate, ticket_type, expiry_date, status)
            VALUES (?, ?, ?, 'monthly', NULL, 'active')
            """,
            (card_id, holder, plate),
        )

    start_month = datetime.now().replace(day=1)

    for i in range(month_count):
        month = start_month.month - i
        year = start_month.year
        while month <= 0:
            month += 12
            year -= 1

        month_label = f"{year:04d}-{month:02d}"
        paid_day = min(28, random.randint(1, 10))
        paid_at = datetime(year, month, paid_day, 9, 0, 0).strftime("%Y-%m-%d %H:%M:%S")

        for card_id, _, _ in monthly_cards:
            cursor.execute(
                """
                INSERT INTO monthly_payments (card_id, month, amount, paid_at)
                VALUES (?, ?, ?, ?)
                """,
                (card_id, month_label, monthly_fee, paid_at),
            )

    print("Đã sinh dữ liệu đóng tiền vé tháng.")

def create_fake_data():
    print(f"Đang kết nối đến database: {DATABASE}")
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # --- SỬA ĐỔI: Lấy giá tiền động từ Database ---
    current_fee = get_current_fee(cursor)
    monthly_fee = get_monthly_fee(cursor)
    print(f"Đang sử dụng mức phí từ cài đặt: {current_fee:,.0f} VNĐ/giờ")
    print(f"Mức phí vé tháng hiện tại: {monthly_fee:,.0f} VNĐ/tháng")
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

    seed_monthly_payments(cursor, monthly_fee)
    conn.commit()
    conn.close()
    print(f"--- HOÀN TẤT! Đã thêm {total_records} giao dịch giả với giá {current_fee:,.0f}đ/h. ---")

if __name__ == '__main__':
    create_fake_data()
