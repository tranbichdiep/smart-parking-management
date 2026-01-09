import os
from datetime import datetime

from flask import Blueprint, Response, current_app, jsonify, request

from app.database import get_db_connection
from app.services.camera import generate_frames
from app.utils import login_required

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/gate/device_scan", methods=["POST"])
def device_scan():
    """
    API xử lý quẹt thẻ từ ESP32.
    """
    conn = None
    try:
        data = request.get_json()
        if not data:
            return jsonify({"action": "wait", "message": "Bad request"}), 400

        if data.get("token") != current_app.config["DEVICE_SECRET_TOKEN"]:
            return jsonify({"action": "wait", "message": "Unauthorized"}), 403

        card_id = data.get("card_id")
        if not card_id:
            return jsonify({"action": "wait", "message": "Missing card_id"}), 400

        conn = get_db_connection()

        # Kiểm tra thẻ tồn tại
        card_info = conn.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()

        if not card_info:
            try:
                conn.execute(
                    "INSERT INTO pending_actions (card_id, status, action_type, created_at) VALUES (?, ?, ?, ?)",
                    (card_id, "alert_unregistered", "alert", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )
                conn.commit()
            except Exception as exc:
                current_app.logger.warning("Lỗi ghi alert thẻ lạ: %s", exc)

            conn.close()
            return jsonify({"action": "wait", "message": "Thẻ không thuộc bãi xe"})

        if card_info["status"] == "lost":
            try:
                conn.execute(
                    "INSERT INTO pending_actions (card_id, status, action_type, created_at) VALUES (?, ?, ?, ?)",
                    (card_id, "alert_lost", "alert", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )
                conn.commit()
            except Exception as exc:
                current_app.logger.warning("Lỗi ghi alert lost-card: %s", exc)

            conn.close()
            return jsonify({"action": "wait", "message": "Thẻ này đã bị báo mất. Vui lòng liên hệ quản lý."})

        active_transaction = conn.execute(
            "SELECT * FROM transactions WHERE card_id = ? AND exit_time IS NULL", (card_id,)
        ).fetchone()

        # === CASE 1: XE RA ===
        if active_transaction:
            exit_time_dt = datetime.now()
            card_type = card_info["ticket_type"]

            entry_time_dt = datetime.strptime(active_transaction["entry_time"], "%Y-%m-%d %H:%M:%S")
            duration = exit_time_dt - entry_time_dt

            fee = 0
            expiry_date_dt = None
            if card_info["expiry_date"]:
                try:
                    expiry_date_dt = datetime.strptime(card_info["expiry_date"], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    expiry_date_dt = None

            should_charge_walkin = card_type == "daily" or (card_type == "monthly" and expiry_date_dt and expiry_date_dt < entry_time_dt)

            if should_charge_walkin:
                settings_data = conn.execute("SELECT * FROM settings").fetchall()
                settings = {row["key"]: row["value"] for row in settings_data}
                fee_per_hour = int(settings.get("fee_per_hour", 5000))

                hours = max(1, -(-duration.total_seconds() // 3600))
                fee = int(hours * fee_per_hour)

            pending = conn.execute(
                """INSERT INTO pending_actions 
                   (card_id, status, action_type, created_at, transaction_id, license_plate, entry_time, duration, fee) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    card_id,
                    "pending",
                    "exit",
                    exit_time_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    active_transaction["id"],
                    active_transaction["license_plate"],
                    active_transaction["entry_time"],
                    str(duration).split(".")[0],
                    fee,
                ),
            )
            conn.commit()
            poll_id = pending.lastrowid
            conn.close()
            return jsonify({"action": "poll", "poll_id": poll_id, "message": "Xe ra, chờ bảo vệ..."})

        # === CASE 2: XE VÀO ===
        pending = conn.execute(
            "INSERT INTO pending_actions (card_id, status, action_type, created_at) VALUES (?, ?, ?, ?)",
            (card_id, "pending", "entry", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        poll_id = pending.lastrowid
        conn.close()
        return jsonify({"action": "poll", "poll_id": poll_id, "message": "Chờ bảo vệ duyệt..."})

    except Exception as exc:
        if conn:
            conn.close()
        current_app.logger.error("Lỗi tại /api/gate/device_scan: %s", exc)
        return jsonify({"action": "wait", "message": "Lỗi server"}), 500


@api_bp.route("/api/gate/check_action_status", methods=["GET"])
def check_action_status():
    """ESP32 poll để kiểm tra bảo vệ đã duyệt chưa."""
    poll_id = request.args.get("id")
    if not poll_id:
        return jsonify({"status": "error"}), 400

    conn = get_db_connection()
    action = conn.execute("SELECT status FROM pending_actions WHERE id = ?", (poll_id,)).fetchone()

    if not action:
        conn.close()
        return jsonify({"status": "denied"})

    status = action["status"]

    if status in ("approved", "denied"):
        conn.execute("DELETE FROM pending_actions WHERE id = ?", (poll_id,))
        conn.commit()

    conn.close()
    return jsonify({"status": status})


@api_bp.route("/video_feed_in")
@login_required
def video_feed_in():
    # Lấy sẵn cấu hình từ app context trước khi vào vòng lặp
    placeholder_path = os.path.join(current_app.static_folder, "placeholder.jpg")
    is_test_mode = current_app.config.get("CAMERA_TEST_MODE", True)
    rtsp_url = current_app.config["RTSP_URL_IN"]

    return Response(
        generate_frames(rtsp_url, placeholder_path, is_test_mode),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@api_bp.route("/video_feed_out")
@login_required
def video_feed_out():
    # Lấy sẵn cấu hình từ app context trước khi vào vòng lặp
    placeholder_path = os.path.join(current_app.static_folder, "placeholder.jpg")
    is_test_mode = current_app.config.get("CAMERA_TEST_MODE", True)
    rtsp_url = current_app.config["RTSP_URL_OUT"]

    return Response(
        generate_frames(rtsp_url, placeholder_path, is_test_mode),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )