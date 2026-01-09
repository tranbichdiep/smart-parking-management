import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR.parent / "database" / "parking.db"
DEFAULT_SNAPSHOT_PATH = BASE_DIR / "static" / "snapshots"

load_dotenv(BASE_DIR / ".env")


def _resolve_path(value: str, default: Path) -> str:
    """Chuyển chuỗi cấu hình sang đường dẫn tuyệt đối (relative tính từ BASE_DIR)."""
    raw_path = Path(value) if value else default
    if not raw_path.is_absolute():
        raw_path = BASE_DIR / raw_path
    return str(raw_path.expanduser().resolve())


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "day_la_mot_chuoi_bi_mat_rat_dai_va_kho_doan")
    DATABASE_PATH = _resolve_path(os.getenv("DATABASE_PATH"), DEFAULT_DB_PATH)
    SNAPSHOT_DIR = _resolve_path(os.getenv("SNAPSHOT_DIR"), DEFAULT_SNAPSHOT_PATH)
    DEVICE_SECRET_TOKEN = os.getenv("DEVICE_SECRET_TOKEN", "my_secret_device_token_12345")
    RTSP_URL_IN = os.getenv("RTSP_URL_IN", "rtsp://admin:admin@192.168.0.101:8554/live")
    RTSP_URL_OUT = os.getenv("RTSP_URL_OUT", "rtsp://admin:admin@192.168.0.103:8554/live")
    CAMERA_TEST_MODE = os.getenv("CAMERA_TEST_MODE", "true").lower() == "true"

    JSON_AS_ASCII = False
    SQLITE_TIMEOUT = float(os.getenv("SQLITE_TIMEOUT", "20.0"))
