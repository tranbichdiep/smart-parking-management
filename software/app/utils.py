import calendar
from datetime import datetime
from functools import wraps
from typing import Callable, Optional

from flask import redirect, session, url_for


def vn_dt(value, fmt: str = "%d/%m/%Y %H:%M:%S") -> Optional[str]:
    """Định dạng thời gian sang kiểu Việt Nam; trả nguyên giá trị nếu không hợp lệ."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime(fmt)
    except Exception:
        return value


def escape_like(value: str) -> str:
    """Escape ký tự wildcard để dùng an toàn với LIKE."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def parse_int_param(raw_value, default: int, max_value: Optional[int] = None) -> int:
    """Chuyển chuỗi sang int với giá trị mặc định và giới hạn tối đa."""
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    if value < 1:
        value = default
    if max_value is not None:
        value = min(value, max_value)
    return value


def add_months(base_date: datetime, months: int) -> datetime:
    """Cộng thêm số tháng, giữ nguyên ngày trong tháng nếu có thể."""
    month = base_date.month - 1 + months
    year = base_date.year + month // 12
    month = month % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return base_date.replace(year=year, month=month, day=day)


def generate_next_employee_code(conn) -> str:
    """Sinh mã nhân viên 6 số (001234) dựa trên mã lớn nhất hiện có."""
    cursor = conn.execute(
        "SELECT MAX(CAST(employee_code AS INTEGER)) FROM users WHERE employee_code GLOB '[0-9][0-9]*'"
    )
    max_code = cursor.fetchone()[0] or 0
    next_code_val = int(max_code) + 1
    if next_code_val > 999999:
        raise ValueError("Đã hết dải mã nhân viên (tối đa 999999).")
    return f"{next_code_val:06d}"


def login_required(view: Callable) -> Callable:
    """Decorator kiểm tra đăng nhập."""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "logged_in" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped_view


def role_required(required_role: str) -> Callable:
    """Decorator kiểm tra quyền (role)."""

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if session.get("role") != required_role:
                return "Bạn không có quyền truy cập.", 403
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def register_template_filters(app):
    """Đăng ký các filter template cần dùng."""
    app.template_filter("vn_dt")(vn_dt)
