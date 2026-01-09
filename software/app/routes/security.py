from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, session, url_for

from app.database import get_db_connection
from app.services.camera import capture_snapshot
from app.utils import login_required, role_required

security_bp = Blueprint("security", __name__)


@security_bp.route("/security/dashboard")
@login_required
@role_required("security")
def security_dashboard():
    return render_template("security_dashboard.html")


@security_bp.route("/api/gate/get_pending_scans", methods=["GET"])
@login_required
@role_required("security")
def get_pending_scans():
    """API Polling: Trả về xe chờ duyệt HOẶC cảnh báo thẻ lạ."""
    conn = get_db_connection()

    # 1. Dọn dẹp các yêu cầu cũ quá 2 phút
    two_min_ago = (datetime.now() - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "DELETE FROM pending_actions WHERE status IN ('pending', 'alert_unregistered', 'alert_lost') AND created_at < ?",
        (two_min_ago,),
    )
    conn.commit()

    # 2. Lấy yêu cầu mới nhất (bao gồm cả 'pending' VÀ 'alert_unregistered')
    pending = conn.execute(
        "SELECT * FROM pending_actions WHERE status IN ('pending', 'alert_unregistered', 'alert_lost') ORDER BY created_at ASC LIMIT 1"
    ).fetchone()

    if pending:
        # === TRƯỜNG HỢP 1: CẢNH BÁO THẺ LẠ ===
        if pending["status"] in ("alert_unregistered", "alert_lost"):
            conn.execute("DELETE FROM pending_actions WHERE id = ?", (pending["id"],))
            conn.commit()
            conn.close()

            alert_message = (
                f"CẢNH BÁO: Thẻ lạ {pending['card_id']}!"
                if pending["status"] == "alert_unregistered"
                else f"THẺ BÁO MẤT: {pending['card_id']} đã bị vô hiệu hóa!"
            )
            return jsonify(
                {
                    "action_type": "alert",
                    "card_id": pending["card_id"],
                    "message": alert_message,
                }
            )

        # === TRƯỜNG HỢP 2: XE CHỜ DUYỆT (Bình thường) ===
        conn.execute("UPDATE pending_actions SET status = 'processing' WHERE id = ?", (pending["id"],))
        conn.commit()

        if pending["action_type"] == "entry":
            card_info = conn.execute(
                "SELECT holder_name, license_plate, ticket_type FROM cards WHERE card_id = ?", (pending["card_id"],)
            ).fetchone()

            holder_name = "Khách vãng lai"
            license_plate = None
            ticket_type = "daily"

            if card_info:
                holder_name = card_info["holder_name"] or "N/A"
                license_plate = card_info["license_plate"]
                ticket_type = card_info["ticket_type"]

            conn.close()
            return jsonify(
                {
                    "poll_id": pending["id"],
                    "action_type": "entry",
                    "card_id": pending["card_id"],
                    "entry_time": datetime.strptime(pending["created_at"], "%Y-%m-%d %H:%M:%S").strftime(
                        "%d/%m/%Y %H:%M:%S"
                    ),
                    "holder_name": holder_name,
                    "license_plate": license_plate,
                    "ticket_type": ticket_type,
                }
            )

        if pending["action_type"] == "exit":
            entry_snapshot = conn.execute("SELECT entry_snapshot FROM transactions WHERE id = ?", (pending["transaction_id"],)).fetchone()
            entry_snapshot_url = (
                f"/static/snapshots/{entry_snapshot['entry_snapshot']}"
                if entry_snapshot and entry_snapshot["entry_snapshot"]
                else url_for("static", filename="placeholder.jpg")
            )
            card_info = conn.execute("SELECT ticket_type FROM cards WHERE card_id = ?", (pending["card_id"],)).fetchone()
            ticket_type = card_info["ticket_type"] if card_info else "daily"

            conn.close()
            return jsonify(
                {
                    "poll_id": pending["id"],
                    "action_type": "exit",
                    "card_id": pending["card_id"],
                    "transaction_id": pending["transaction_id"],
                    "license_plate": pending["license_plate"],
                    "entry_time": pending["entry_time"],
                    "exit_time": datetime.strptime(pending["created_at"], "%Y-%m-%d %H:%M:%S").strftime(
                        "%d/%m/%Y %H:%M:%S"
                    ),
                    "duration": pending["duration"],
                    "fee": pending["fee"],
                    "entry_snapshot_url": entry_snapshot_url,
                    "ticket_type": ticket_type,
                }
            )

    conn.close()
    return jsonify(None)


@security_bp.route("/api/confirm_pending_entry", methods=["POST"])
@login_required
@role_required("security")
def confirm_pending_entry():
    """Bảo vệ nhấn 'XÁC NHẬN VÀO'. API này tạo giao dịch và 'thả' cho ESP32 mở cổng."""
    data = request.get_json()
    poll_id = data["poll_id"]
    card_id = data["card_id"]
    license_plate = data["license_plate"]
    conn = get_db_connection()
    try:
        entry_snapshot_filename = capture_snapshot(card_id, "in")
        entry_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        card_info = conn.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
        if not card_info:
            conn.execute(
                "INSERT INTO cards (card_id, holder_name, ticket_type, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (card_id, f"Khách vãng lai {license_plate}", "daily", "active", entry_time),
            )

        conn.execute(
            "INSERT INTO transactions (card_id, license_plate, entry_time, security_user, entry_snapshot) VALUES (?, ?, ?, ?, ?)",
            (card_id, license_plate, entry_time, session["username"], entry_snapshot_filename),
        )

        conn.execute("UPDATE pending_actions SET status = 'approved' WHERE id = ?", (poll_id,))
        conn.commit()
        return jsonify({"status": "success", "message": f"Đã ghi nhận xe {license_plate} vào bãi."})
    except Exception as exc:
        conn.rollback()
        return jsonify({"status": "error", "message": str(exc)}), 500
    finally:
        conn.close()


@security_bp.route("/api/cancel_pending_action", methods=["POST"])
@login_required
@role_required("security")
def cancel_pending_action():
    """Bảo vệ nhấn 'HỦY' (Dùng chung cho cả VÀO và RA)."""
    data = request.get_json()
    poll_id = data["poll_id"]
    conn = get_db_connection()
    conn.execute("UPDATE pending_actions SET status = 'denied' WHERE id = ?", (poll_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})


@security_bp.route("/api/confirm_pending_exit", methods=["POST"])
@login_required
@role_required("security")
def confirm_pending_exit():
    """Bảo vệ nhấn 'XÁC NHẬN THU TIỀN' (Xe Ra)."""
    data = request.get_json()
    poll_id = data["poll_id"]
    transaction_id = data["transaction_id"]
    fee = data["fee"]

    conn = get_db_connection()
    try:
        transaction = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
        if not transaction or transaction["exit_time"] is not None:
            conn.close()
            return jsonify({"message": "Giao dịch không tồn tại hoặc đã được xử lý."}), 404

        exit_snapshot_filename = capture_snapshot(transaction["card_id"], "out")
        exit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn.execute(
            "UPDATE transactions SET exit_time = ?, fee = ?, security_user = ?, exit_snapshot = ? WHERE id = ?",
            (exit_time, fee, session["username"], exit_snapshot_filename, transaction_id),
        )

        conn.execute("UPDATE pending_actions SET status = 'approved' WHERE id = ?", (poll_id,))
        conn.commit()
        return jsonify({"status": "success", "message": "Giao dịch thành công!"})
    except Exception as exc:
        conn.rollback()
        return jsonify({"status": "error", "message": str(exc)}), 500
    finally:
        conn.close()
