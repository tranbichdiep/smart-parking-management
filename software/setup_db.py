import sqlite3
from typing import List

from werkzeug.security import generate_password_hash

from config import Config

DATABASE = Config.DATABASE_PATH


def _get_columns(cursor: sqlite3.Cursor, table: str) -> List[str]:
    cursor.execute(f"PRAGMA table_info({table});")
    return [row[1] for row in cursor.fetchall()]


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
            status TEXT DEFAULT 'active',
            employee_code TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL
        );
        """)
        user_columns = _get_columns(cursor, "users")
        if 'status' not in user_columns:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active';")
                print("Đã thêm cột 'status' vào bảng users.")
            except sqlite3.OperationalError:
                pass # Cột đã tồn tại, bỏ qua

        # Bổ sung thông tin nhân viên
        if 'employee_code' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN employee_code TEXT;")
            print("Đã thêm cột 'employee_code' vào bảng users.")
        if 'full_name' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN full_name TEXT;")
            print("Đã thêm cột 'full_name' vào bảng users.")

        # Chuẩn hóa dữ liệu nhân viên hiện có, sinh mã nếu thiếu
        cursor.execute("SELECT username, employee_code, full_name FROM users ORDER BY username;")
        rows = cursor.fetchall()

        valid_codes = []
        for _, code, _ in rows:
            if code and str(code).isdigit():
                num_val = int(code)
                if 1 <= num_val <= 999999:
                    valid_codes.append(num_val)
        max_code_val = max(valid_codes) if valid_codes else 0
        assigned_codes = set()

        def next_code() -> str:
            nonlocal max_code_val
            while True:
                max_code_val += 1
                if max_code_val > 999999:
                    raise ValueError("Đã hết dải mã nhân viên (tới 999999).")
                if max_code_val not in assigned_codes:
                    assigned_codes.add(max_code_val)
                    return f"{max_code_val:06d}"

        for username, code, full_name in rows:
            needs_update = False
            normalized_name = (full_name or '').strip() or username

            normalized_code = None
            if code and str(code).isdigit():
                num_val = int(code)
                if 1 <= num_val <= 999999 and num_val not in assigned_codes:
                    normalized_code = f"{num_val:06d}"
                    assigned_codes.add(num_val)
                    max_code_val = max(max_code_val, num_val)
                    if normalized_code != code:
                        needs_update = True
                else:
                    normalized_code = next_code()
                    needs_update = True
            else:
                normalized_code = next_code()
                needs_update = True

            if not full_name or not full_name.strip():
                needs_update = True

            if needs_update:
                cursor.execute(
                    "UPDATE users SET employee_code = ?, full_name = ? WHERE username = ?",
                    (normalized_code, normalized_name, username)
                )
                print(f"Chuẩn hóa nhân viên {username}: code={normalized_code}, name={normalized_name}")

        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_employee_code ON users(employee_code);")
        except sqlite3.OperationalError as exc:
            print(f"Không thể tạo index employee_code (có thể do dữ liệu trùng): {exc}")
        print("Đã tạo/cập nhật bảng 'users'.")
        existing_usernames = {username for username, _, _ in rows}

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

        if 'admin' not in existing_usernames:
            admin_code = next_code()
            cursor.execute(
                "INSERT INTO users (username, password_hash, role, status, employee_code, full_name) VALUES (?, ?, ?, 'active', ?, ?)", 
                ('admin', admin_pass, 'admin', admin_code, 'Admin')
            )
            print(f"Đã thêm tài khoản mẫu 'admin' với mã {admin_code}.")

        if 'baove' not in existing_usernames:
            security_code = next_code()
            cursor.execute(
                "INSERT INTO users (username, password_hash, role, status, employee_code, full_name) VALUES (?, ?, ?, 'active', ?, ?)", 
                ('baove', security_pass, 'security', security_code, 'Bảo vệ')
            )
            print(f"Đã thêm tài khoản mẫu 'baove' với mã {security_code}.")

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
