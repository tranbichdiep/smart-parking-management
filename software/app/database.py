import sqlite3
from flask import current_app


def get_db_connection() -> sqlite3.Connection:
    """Trả về kết nối SQLite với cấu hình chung."""
    conn = sqlite3.connect(
        current_app.config["DATABASE_PATH"],
        timeout=current_app.config.get("SQLITE_TIMEOUT", 20.0),
    )
    conn.row_factory = sqlite3.Row
    return conn
