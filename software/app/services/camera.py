import os
import shutil
import time
import logging
from datetime import datetime

import cv2
from flask import current_app

# Sử dụng logger chuẩn của Python để tránh lỗi context của Flask
logger = logging.getLogger(__name__)

def _ensure_snapshot_dir() -> str:
    snapshot_dir = current_app.config["SNAPSHOT_DIR"]
    os.makedirs(snapshot_dir, exist_ok=True)
    return snapshot_dir


def _copy_placeholder(placeholder_path: str, destination_path: str, fallback_name: str) -> str:
    """Copy ảnh placeholder sang thư mục snapshot, trả về tên file."""
    if not os.path.exists(placeholder_path):
        return fallback_name
    try:
        shutil.copy(placeholder_path, destination_path)
        return os.path.basename(destination_path)
    except Exception as exc:
        logger.warning("Không thể copy placeholder: %s", exc)
        return fallback_name


def capture_snapshot(card_id: str, event_type: str) -> str:
    """
    Chụp ảnh từ camera RTSP (hoặc sinh ảnh giả lập nếu bật CAMERA_TEST_MODE).
    Hàm này chạy trong request context nên vẫn dùng current_app được.
    """
    snapshot_dir = _ensure_snapshot_dir()
    placeholder_path = os.path.join(current_app.static_folder, "placeholder.jpg")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{card_id}_{timestamp}_{event_type}.jpg"
    destination_path = os.path.join(snapshot_dir, filename)

    # Chế độ test: luôn dùng ảnh placeholder để tránh phụ thuộc phần cứng.
    if current_app.config.get("CAMERA_TEST_MODE", True):
        offline_name = f"{card_id}_{timestamp}_{event_type}_offline.jpg"
        offline_path = os.path.join(snapshot_dir, offline_name)
        return _copy_placeholder(placeholder_path, offline_path, offline_name)

    rtsp_url = current_app.config["RTSP_URL_IN"]
    if event_type == "out":
        rtsp_url = current_app.config["RTSP_URL_OUT"]

    cap = None
    try:
        cap = cv2.VideoCapture(rtsp_url)
        # Xóa buffer đầu vào cho ổn định
        for _ in range(5):
            cap.read()

        ret, frame = cap.read()
        if not ret or frame is None:
            raise RuntimeError(f"Không thể đọc frame từ {rtsp_url}")

        cv2.imwrite(destination_path, frame)
        return filename
    except Exception as exc:
        logger.warning("Lỗi chụp ảnh từ %s: %s", rtsp_url, exc)
        offline_name = f"{card_id}_{timestamp}_{event_type}_offline.jpg"
        offline_path = os.path.join(snapshot_dir, offline_name)
        return _copy_placeholder(placeholder_path, offline_path, offline_name)
    finally:
        if cap:
            cap.release()


def _encode_image(path: str):
    if not os.path.exists(path):
        return None
    try:
        frame = cv2.imread(path)
        if frame is None:
            return None
        flag, encoded = cv2.imencode(".jpg", frame)
        if not flag:
            return None
        return bytearray(encoded)
    except Exception as exc:
        logger.warning("Không thể đọc placeholder %s: %s", path, exc)
        return None


def generate_frames(rtsp_url: str, placeholder_path: str, is_test_mode: bool):
    """
    Trả về stream MJPEG.
    Đã loại bỏ current_app để tránh lỗi Working outside of application context.
    Tham số được truyền trực tiếp từ bên ngoài vào.
    """
    cap = None

    while True:
        if is_test_mode:
            encoded = _encode_image(placeholder_path)
            if encoded:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + encoded + b"\r\n"
                )
            time.sleep(1)
            continue

        try:
            if cap is None:
                logger.info("Kết nối camera: %s", rtsp_url)
                cap = cv2.VideoCapture(rtsp_url)
                if not cap.isOpened():
                    raise ConnectionError(f"Không thể mở stream: {rtsp_url}")

            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning("Mất kết nối %s. Đang thử lại...", rtsp_url)
                cap.release()
                cap = None
                time.sleep(2)
                continue

            frame_resized = cv2.resize(frame, (640, 480))
            flag, encoded_image = cv2.imencode(".jpg", frame_resized)
            if not flag:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + bytearray(encoded_image) + b"\r\n"
            )

        except Exception as exc:
            logger.warning("Lỗi stream %s: %s", rtsp_url, exc)
            if cap:
                cap.release()
            cap = None

            encoded = _encode_image(placeholder_path)
            if encoded:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + encoded + b"\r\n"
                )
            time.sleep(5)