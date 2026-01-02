import time
from datetime import datetime, timedelta

from flask import render_template, request, session, jsonify, Response, url_for
import cv2

from auth import login_required, role_required
from core import (
    get_db_connection,
    capture_snapshot,
    DEVICE_SECRET_TOKEN,
    RTSP_URL_IN,
    RTSP_URL_OUT,
)


def generate_frames(rtsp_url):
    cap = None
    while True:
        try:
            if cap is None:
                print(f"Đang kết nối đến camera: {rtsp_url}")
                cap = cv2.VideoCapture(rtsp_url)
                if not cap.isOpened():
                    raise ConnectionError(f"Không thể mở stream: {rtsp_url}")
                print(f"Đã kết nối camera: {rtsp_url}")

            ret, frame = cap.read()
            if not ret or frame is None:
                print(f"Mất kết nối {rtsp_url}. Đang thử kết nối lại...")
                cap.release()
                cap = None
                time.sleep(2) 
                continue

            frame_resized = cv2.resize(frame, (640, 480))
            (flag, encodedImage) = cv2.imencode(".jpg", frame_resized)
            if not flag:
                continue

            yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 
                  bytearray(encodedImage) + b'\r\n')
        
        except ConnectionError as e:
            print(e)
            error_frame = cv2.vconcat([cv2.vconcat([cv2.Mat(480, 640, cv2.CV_8UC3, (50, 50, 50))])])
            cv2.putText(error_frame, 'CAMERA OFFLINE', (180, 250), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            (flag, encodedImage) = cv2.imencode(".jpg", error_frame)
            if flag:
                yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 
                      bytearray(encodedImage) + b'\r\n')
            time.sleep(5) 
        
        except Exception as e:
            print(f"Lỗi không xác định trong generate_frames ({rtsp_url}): {e}")
            if cap:
                cap.release()
            cap = None
            time.sleep(5)


def register_security_routes(app):
    # ======================================================
    # --- TRANG BẢO VỆ (SECURITY DASHBOARD) ---
    # ======================================================

    @app.route('/security/dashboard')
    @login_required
    @role_required('security')
    def security_dashboard():
        return render_template('security_dashboard.html')

    # ======================================================
    # --- API CHO GIAO DIỆN WEB BẢO VỆ ---
    # ======================================================

    @app.route('/api/gate/get_pending_scans', methods=['GET'])
    @login_required
    @role_required('security')
    def get_pending_scans():
        """API Polling: Trả về xe chờ duyệt HOẶC cảnh báo thẻ lạ."""
        conn = get_db_connection()
        
        # 1. Dọn dẹp các yêu cầu cũ quá 2 phút
        two_min_ago = (datetime.now() - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("DELETE FROM pending_actions WHERE status IN ('pending', 'alert_unregistered', 'alert_lost') AND created_at < ?", (two_min_ago,))
        conn.commit()

        # 2. Lấy yêu cầu mới nhất (bao gồm cả 'pending' VÀ 'alert_unregistered')
        pending = conn.execute(
            "SELECT * FROM pending_actions WHERE status IN ('pending', 'alert_unregistered', 'alert_lost') ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        
        if pending:
            # === TRƯỜNG HỢP 1: CẢNH BÁO THẺ LẠ ===
            if pending['status'] in ('alert_unregistered', 'alert_lost'):
                # Xóa ngay bản ghi này để không báo lại liên tục
                conn.execute("DELETE FROM pending_actions WHERE id = ?", (pending['id'],))
                conn.commit()
                conn.close()
                
                # Trả về JSON đặc biệt loại 'alert'
                alert_message = f"CẢNH BÁO: Thẻ lạ {pending['card_id']}!" if pending['status'] == 'alert_unregistered' else f"THẺ BÁO MẤT: {pending['card_id']} đã bị vô hiệu hóa!"
                return jsonify({
                    "action_type": "alert",
                    "card_id": pending['card_id'],
                    "message": alert_message
                })

            # === TRƯỜNG HỢP 2: XE CHỜ DUYỆT (Bình thường) ===
            # Đánh dấu 'processing' để không bị lấy lặp lại
            conn.execute("UPDATE pending_actions SET status = 'processing' WHERE id = ?", (pending['id'],))
            conn.commit()

            if pending['action_type'] == 'entry':
                # Lấy thông tin bổ sung từ thẻ
                card_info = conn.execute("SELECT holder_name, license_plate, ticket_type FROM cards WHERE card_id = ?", (pending['card_id'],)).fetchone()
                
                holder_name = "Khách vãng lai"
                license_plate = None
                ticket_type = "daily"

                if card_info:
                    holder_name = card_info['holder_name'] or "N/A"
                    license_plate = card_info['license_plate']
                    ticket_type = card_info['ticket_type']
                
                conn.close()
                return jsonify({
                    "poll_id": pending['id'],
                    "action_type": "entry",
                    "card_id": pending['card_id'],
                    "entry_time": datetime.strptime(pending['created_at'], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M:%S"),
                    "holder_name": holder_name,
                    "license_plate": license_plate,
                    "ticket_type": ticket_type
                })

            elif pending['action_type'] == 'exit':
                # Tìm ảnh lúc vào để đối chiếu
                entry_snapshot = conn.execute('SELECT entry_snapshot FROM transactions WHERE id = ?', (pending['transaction_id'],)).fetchone()
                entry_snapshot_url = f"/static/snapshots/{entry_snapshot['entry_snapshot']}" if entry_snapshot and entry_snapshot['entry_snapshot'] else url_for('static', filename='placeholder.jpg')
                card_info = conn.execute('SELECT ticket_type FROM cards WHERE card_id = ?', (pending['card_id'],)).fetchone()
                ticket_type = card_info['ticket_type'] if card_info else 'daily'
                
                conn.close()
                return jsonify({
                    "poll_id": pending['id'],
                    "action_type": "exit",
                    "card_id": pending['card_id'],
                    "transaction_id": pending['transaction_id'],
                    "license_plate": pending['license_plate'],
                    "entry_time": pending['entry_time'],
                    "exit_time": datetime.strptime(pending['created_at'], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M:%S"),
                    "duration": pending['duration'],
                    "fee": pending['fee'],
                    "entry_snapshot_url": entry_snapshot_url,
                    "ticket_type": ticket_type
                })
                
        conn.close()
        return jsonify(None) # Không có gì mới

    @app.route('/api/confirm_pending_entry', methods=['POST'])
    @login_required
    @role_required('security')
    def confirm_pending_entry():
        """Bảo vệ nhấn 'XÁC NHẬN VÀO'. API này tạo giao dịch và 'thả' cho ESP32 mở cổng."""
        data = request.get_json()
        poll_id = data['poll_id']
        card_id = data['card_id']
        license_plate = data['license_plate']
        conn = get_db_connection()
        try:
            # 1. Tạo giao dịch (HÀM NÀY ĐÃ ĐƯỢC SỬA ĐỂ CHỤP ẢNH THẬT TỪ CAM VÀO)
            entry_snapshot_filename = capture_snapshot(card_id, 'in')
            entry_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Tạo thẻ vãng lai nếu chưa có (Với logic mới, đoạn này ít khi chạy nhưng cứ để phòng hờ)
            card_info = conn.execute('SELECT * FROM cards WHERE card_id = ?', (card_id,)).fetchone()
            if not card_info:
                conn.execute(
                    'INSERT INTO cards (card_id, holder_name, ticket_type, status, created_at) VALUES (?, ?, ?, ?, ?)',
                    (card_id, f'Khách vãng lai {license_plate}', 'daily', 'active', entry_time)
                )

            conn.execute(
                'INSERT INTO transactions (card_id, license_plate, entry_time, security_user, entry_snapshot) VALUES (?, ?, ?, ?, ?)',
                (card_id, license_plate, entry_time, session['username'], entry_snapshot_filename)
            )
            
            # 2. Đánh dấu 'approved' để ESP32 mở cổng
            conn.execute("UPDATE pending_actions SET status = 'approved' WHERE id = ?", (poll_id,))
            conn.commit()
            return jsonify({'status': 'success', 'message': f'Đã ghi nhận xe {license_plate} vào bãi.'})
        except Exception as e:
            conn.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            conn.close()

    @app.route('/api/cancel_pending_action', methods=['POST'])
    @login_required
    @role_required('security')
    def cancel_pending_action():
        """Bảo vệ nhấn 'HỦY' (Dùng chung cho cả VÀO và RA)."""
        data = request.get_json()
        poll_id = data['poll_id']
        conn = get_db_connection()
        # Đánh dấu 'denied' để ESP32 báo lỗi
        conn.execute("UPDATE pending_actions SET status = 'denied' WHERE id = ?", (poll_id,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})

    @app.route('/api/confirm_pending_exit', methods=['POST'])
    @login_required
    @role_required('security')
    def confirm_pending_exit():
        """Bảo vệ nhấn 'XÁC NHẬN THU TIỀN' (Xe Ra)."""
        data = request.get_json()
        poll_id = data['poll_id']
        transaction_id = data['transaction_id']
        fee = data['fee']
        
        conn = get_db_connection()
        try:
            transaction = conn.execute( 'SELECT * FROM transactions WHERE id = ?', (transaction_id,)).fetchone()
            if not transaction or transaction['exit_time'] is not None:
                conn.close()
                return jsonify({'message': 'Giao dịch không tồn tại hoặc đã được xử lý.'}), 404

            # CHỤP ẢNH THẬT LÚC RA TỪ CAM RA
            exit_snapshot_filename = capture_snapshot(transaction['card_id'], 'out')
            exit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 1. Cập nhật giao dịch
            conn.execute(
                'UPDATE transactions SET exit_time = ?, fee = ?, security_user = ?, exit_snapshot = ? WHERE id = ?',
                (exit_time, fee, session['username'], exit_snapshot_filename, transaction_id)
            )
            
            # 2. Đánh dấu 'approved' để ESP32 mở cổng
            conn.execute("UPDATE pending_actions SET status = 'approved' WHERE id = ?", (poll_id,))
            conn.commit()
            return jsonify({'status': 'success', 'message': 'Giao dịch thành công!'})
        except Exception as e:
            conn.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            conn.close()

    # ======================================================
    # --- API CHO THIẾT BỊ (ESP32) ---
    # ======================================================

    @app.route('/api/gate/device_scan', methods=['POST'])
    def device_scan():
        """
        API xử lý quẹt thẻ từ ESP32.
        CẬP NHẬT: Ghi log 'alert_unregistered' vào DB để báo lên Web nếu thẻ lạ.
        """
        conn = None
        try:
            data = request.get_json()
            if not data:
                return jsonify({"action": "wait", "message": "Bad request"}), 400
            
            # 1. Xác thực Token
            if data.get('token') != DEVICE_SECRET_TOKEN:
                return jsonify({"action": "wait", "message": "Unauthorized"}), 403
                
            card_id = data.get('card_id')
            if not card_id:
                return jsonify({"action": "wait", "message": "Missing card_id"}), 400

            conn = get_db_connection()

            # ==================================================================
            # [QUAN TRỌNG] KIỂM TRA THẺ CÓ TRONG HỆ THỐNG KHÔNG?
            # ==================================================================
            card_info = conn.execute('SELECT * FROM cards WHERE card_id = ?', (card_id,)).fetchone()

            if not card_info:
                # === NẾU THẺ LẠ: GHI CẢNH BÁO VÀO DB ĐỂ WEB HIỂN THỊ ===
                try:
                    conn.execute(
                        "INSERT INTO pending_actions (card_id, status, action_type, created_at) VALUES (?, ?, ?, ?)",
                        (card_id, 'alert_unregistered', 'alert', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )
                    conn.commit()
                except Exception as e:
                    print(f"Lỗi ghi alert: {e}")

                conn.close()
                print(f"🚫 Đã chặn thẻ lạ: {card_id} (Đã gửi cảnh báo lên Web)")
                
                # Trả về 'wait' để ESP32 báo lỗi đèn đỏ/còi
                return jsonify({
                    "action": "wait", 
                    "message": "Thẻ không thuộc bãi xe"
                })
            # ==================================================================

            # ==================================================================
            # CHẶN THẺ BÁO MẤT
            # ==================================================================
            if card_info['status'] == 'lost':
                try:
                    conn.execute(
                        "INSERT INTO pending_actions (card_id, status, action_type, created_at) VALUES (?, ?, ?, ?)",
                        (card_id, 'alert_lost', 'alert', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )
                    conn.commit()
                except Exception as e:
                    print(f"Lỗi ghi alert lost-card: {e}")

                conn.close()
                print(f"🚫 Thẻ {card_id} đang ở trạng thái MẤT THẺ. Đã báo lên Web.")
                return jsonify({
                    "action": "wait",
                    "message": "Thẻ này đã bị báo mất. Vui lòng liên hệ quản lý."
                })
            # ==================================================================

            # 2. Kiểm tra thẻ đang ở trong hay ngoài (để xác định là Vào hay Ra)
            active_transaction = conn.execute(
                'SELECT * FROM transactions WHERE card_id = ? AND exit_time IS NULL', (card_id,)
            ).fetchone()
                
            # === CASE 1: XE RA (Đã có giao dịch vào chưa kết thúc) ===
            if active_transaction:
                exit_time_dt = datetime.now()
                card_type = card_info['ticket_type'] # Lấy thông tin loại vé
                
                # Tính toán thời gian
                entry_time_dt = datetime.strptime(active_transaction['entry_time'], "%Y-%m-%d %H:%M:%S")
                duration = exit_time_dt - entry_time_dt

                # Tính phí (vãng lai hoặc vé tháng đã hết hạn)
                fee = 0
                expiry_date_dt = None
                if card_info['expiry_date']:
                    try:
                        expiry_date_dt = datetime.strptime(card_info['expiry_date'], "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        expiry_date_dt = None

                should_charge_walkin = card_type == 'daily' or (card_type == 'monthly' and expiry_date_dt and expiry_date_dt < entry_time_dt)

                if should_charge_walkin:
                    settings_data = conn.execute('SELECT * FROM settings').fetchall()
                    settings = {row['key']: row['value'] for row in settings_data}
                    fee_per_hour = int(settings.get('fee_per_hour', 5000))
                    
                    hours = max(1, -(-duration.total_seconds() // 3600)) 
                    fee = int(hours * fee_per_hour)
                
                # Tạo yêu cầu 'exit'
                pending = conn.execute(
                    """INSERT INTO pending_actions 
                       (card_id, status, action_type, created_at, transaction_id, license_plate, entry_time, duration, fee) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (card_id, 'pending', 'exit', exit_time_dt.strftime("%Y-%m-%d %H:%M:%S"), 
                     active_transaction['id'], active_transaction['license_plate'], 
                     active_transaction['entry_time'], str(duration).split('.')[0], fee)
                )
                conn.commit()
                poll_id = pending.lastrowid
                conn.close()
                return jsonify({'action': 'poll', 'poll_id': poll_id, 'message': 'Xe ra, chờ bảo vệ...'})

            # === CASE 2: XE VÀO (Chưa có giao dịch active) ===
            else:
                # Tạo yêu cầu 'entry'
                pending = conn.execute(
                    "INSERT INTO pending_actions (card_id, status, action_type, created_at) VALUES (?, ?, ?, ?)",
                    (card_id, 'pending', 'entry', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                conn.commit()
                poll_id = pending.lastrowid
                conn.close()
                return jsonify({'action': 'poll', 'poll_id': poll_id, 'message': 'Chờ bảo vệ duyệt...'})

        except Exception as e:
            if conn:
                conn.close()
            print(f"Lỗi tại /api/gate/device_scan: {e}")
            return jsonify({"action": "wait", "message": "Lỗi server"}), 500


    @app.route('/api/gate/check_action_status', methods=['GET'])
    def check_action_status():
        """API này được ESP32 gọi (poll) để kiểm tra xem bảo vệ đã duyệt chưa."""
        poll_id = request.args.get('id')
        if not poll_id:
            return jsonify({"status": "error"}), 400
            
        conn = get_db_connection()
        action = conn.execute("SELECT status FROM pending_actions WHERE id = ?", (poll_id,)).fetchone()
        
        if not action:
            conn.close()
            return jsonify({"status": "denied"}) 

        status = action['status']
        
        if status == 'approved' or status == 'denied':
            # Xóa hành động đã hoàn thành
            conn.execute("DELETE FROM pending_actions WHERE id = ?", (poll_id,))
            conn.commit()
            
        conn.close()
        return jsonify({"status": status}) 

    # ======================================================
    # --- API TRUYỀN VIDEO CHO WEB ---
    # ======================================================

    @app.route('/video_feed_in')
    @login_required
    def video_feed_in():
        return Response(generate_frames(RTSP_URL_IN),
                        mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.route('/video_feed_out')
    @login_required
    def video_feed_out():
        return Response(generate_frames(RTSP_URL_OUT),
                        mimetype='multipart/x-mixed-replace; boundary=frame')
