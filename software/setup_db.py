import sqlite3
import os
from werkzeug.security import generate_password_hash

# --- Cấu hình đường dẫn Database ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, '..', 'database', 'parking.db')


def setup_database():
    """Hàm này sẽ tạo/cập nhật các bảng và chèn dữ liệu mẫu."""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        print("Đã kết nối đến database.")

        # --- Tạo/Cập nhật bảng users ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        );
        """)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active';")
            print("Đã thêm cột 'status' vào bảng users.")
        except sqlite3.OperationalError:
            pass # Cột đã tồn tại, bỏ qua
        print("Đã tạo/cập nhật bảng 'users'.")

        # --- Tạo/Cập nhật bảng cards ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            card_id TEXT PRIMARY KEY NOT NULL,
            holder_name TEXT,
            license_plate TEXT,
            ticket_type TEXT NOT NULL,
            expiry_date TEXT,
            created_at TEXT,
            status TEXT NOT NULL
        );
        """)
        print("Đã tạo/cập nhật bảng 'cards'.")

        try:
            cursor.execute("ALTER TABLE cards ADD COLUMN license_plate TEXT;")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE cards ADD COLUMN created_at TEXT;")
        except sqlite3.OperationalError:
            pass

        # --- Tạo/Cập nhật bảng settings ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL
        );
        """)
        print("Đã tạo/cập nhật bảng 'settings'.")

        # --- Tạo/Cập nhật bảng transactions ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT NOT NULL,
            license_plate TEXT, 
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            fee INTEGER,
            entry_snapshot TEXT,
            exit_snapshot TEXT,
            security_user TEXT
        );
        """)
        print("Đã tạo/cập nhật bảng 'transactions'.")
        
        try:
            cursor.execute("ALTER TABLE transactions ADD COLUMN license_plate TEXT;")
        except sqlite3.OperationalError:
            pass

        # --- Bảng đóng tiền vé tháng ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS monthly_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT NOT NULL,
            month TEXT NOT NULL,          -- Định dạng YYYY-MM
            amount INTEGER NOT NULL,
            paid_at TEXT NOT NULL         -- Thời điểm thanh toán
        );
        """)
        print("Đã tạo/cập nhật bảng 'monthly_payments'.")

        # --- MỚI: Bảng chờ duyệt (pending_actions) ---
        # Đã cập nhật để xử lý cả VÀO và RA
        cursor.execute("DROP TABLE IF EXISTS pending_actions;") # Xóa bảng cũ nếu có
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT NOT NULL,
            status TEXT NOT NULL,            -- 'pending', 'processing', 'approved', 'denied'
            action_type TEXT NOT NULL,      -- 'entry' hoặc 'exit'
            created_at TEXT NOT NULL,
            
            -- Dữ liệu cho 'exit'
            transaction_id INTEGER,         -- ID của giao dịch gốc
            license_plate TEXT,             -- Biển số lúc vào
            entry_time TEXT,                -- Giờ vào
            duration TEXT,                  -- Tổng thời gian
            fee INTEGER                     -- Phí phải trả
        );
        """)
        print("Đã tạo/cập nhật bảng 'pending_actions'.")

        # --- Chèn dữ liệu mẫu ---
        admin_pass = generate_password_hash('123456')
        security_pass = generate_password_hash('123456')

        cursor.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)", 
                       ('admin', admin_pass, 'admin'))
        cursor.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)", 
                       ('baove', security_pass, 'security'))
        print("Đã chèn dữ liệu mẫu cho 'admin' và 'baove'.")

        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('monthly_fee', '1200000'))
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('fee_per_hour', '10000'))
        print("Đã chèn dữ liệu cài đặt mặc định.")

        conn.commit()
        conn.close()
        print("Thiết lập database hoàn tất!")

    except Exception as e:
        print(f"Đã xảy ra lỗi: {e}")

if __name__ == '__main__':
    setup_database()
