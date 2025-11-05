# --- Import các thư viện cần thiết ---
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash, Response
import sqlite3
import os
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from datetime import datetime, timedelta
import shutil 
import cv2 # <-- MỚI: Thêm thư viện OpenCV
import time # <-- MỚI: Dùng cho bộ đệm camera

# --- Khởi tạo ứng dụng Flask ---
app = Flask(__name__)

# --- Cấu hình ---
app.secret_key = 'day_la_mot_chuoi_bi_mat_rat_dai_va_kho_doan' 

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, '..', 'database', 'parking.db')
SNAPSHOT_DIR = os.path.join(BASE_DIR, 'static', 'snapshots') 
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

# *** MỚI: Token bí mật cho các thiết bị ESP32 ***
DEVICE_SECRET_TOKEN = "my_secret_device_token_12345"

# *** MỚI: Cấu hình 2 Camera RTSP ***
RTSP_URL_IN = "rtsp://admin:admin@192.168.0.102:8554/live"
RTSP_URL_OUT = "rtsp://admin:admin@192.168.0.103:8554/live"
# RTSP_URL_IN = "rtsp://admin:admin@ace-3v-4t3kx75a.local:8554/live"
# RTSP_URL_OUT = "rtsp://admin:admin@spid3r-tab.local:8554/live"

@app.template_filter('vn_dt')
def vn_dt(value, fmt="%d/%m/%Y %H:%M:%S"):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime(fmt)
    except Exception:
        return value

# --- Hàm hỗ trợ ---
def get_db_connection():
    # SỬA LỖI "database is locked"
    conn = sqlite3.connect(DATABASE, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn

# --- HÀM CHỤP ẢNH ĐƯỢC CẬP NHẬT ĐỂ DÙNG 2 CAMERA ---
def capture_snapshot(card_id, event_type):
    """
    Kết nối đến RTSP, chụp một khung hình và lưu lại.
    Trả về tên file nếu thành công, hoặc tên file placeholder nếu thất bại.
    """
    placeholder_filename = "placeholder.jpg" # Tên file dự phòng
    
    # === THAY ĐỔI: Chọn đúng URL camera ===
    if event_type == 'in':
        rtsp_url = RTSP_URL_IN
        print(f"Chụp ảnh VÀO từ: {rtsp_url}")
    elif event_type == 'out':
        rtsp_url = RTSP_URL_OUT
        print(f"Chụp ảnh RA từ: {rtsp_url}")
    else:
        rtsp_url = RTSP_URL_IN # Mặc định
    # ======================================
    
    cap = None
    try:
        # 1. Kết nối đến camera
        cap = cv2.VideoCapture(rtsp_url)
        
        # Thử đọc 5 khung hình đầu để xóa bộ đệm (buffer)
        for _ in range(5):
            cap.read()
            
        ret, frame = cap.read() # Đọc khung hình chính
        
        if not ret or frame is None:
            print(f"Lỗi: Không thể đọc frame từ camera RTSP: {rtsp_url}")
            raise Exception("Không thể đọc frame")

        # 2. Tạo tên file và đường dẫn
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{card_id}_{timestamp}_{event_type}.jpg"
        destination_path = os.path.join(SNAPSHOT_DIR, filename)

        # 3. Lưu ảnh
        cv2.imwrite(destination_path, frame)
        print(f"Đã lưu ảnh chụp: {filename}")
        return filename

    except Exception as e:
        print(f"Lỗi khi chụp ảnh từ {rtsp_url}: {e}. Sử dụng ảnh placeholder.")
        # Nếu có lỗi, copy ảnh placeholder
        placeholder_path_src = os.path.join(BASE_DIR, 'static', placeholder_filename)
        if not os.path.exists(placeholder_path_src):
            try:
                # Tạo placeholder nếu chưa có
                img = cv2.vconcat([cv2.vconcat([cv2.Mat(100, 300, cv2.CV_8UC3, (128, 128, 128))])])
                cv2.putText(img, 'CAMERA OFFLINE', (50, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.imwrite(placeholder_path_src, img)
            except: pass # Bỏ qua nếu không tạo được
        
        # Copy file placeholder đến đúng vị trí
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{card_id}_{timestamp}_{event_type}_offline.jpg"
        destination_path = os.path.join(SNAPSHOT_DIR, filename)
        try:
            shutil.copy(placeholder_path_src, destination_path)
        except:
             return placeholder_filename # Trả về placeholder gốc
        return filename # Trả về file placeholder đã copy

    finally:
        # 4. Luôn giải phóng camera
        if cap:
            cap.release()

# --- Decorators để bảo vệ Route ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(required_role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('role') != required_role:
                return "Bạn không có quyền truy cập.", 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Routes cho Xác thực & Điều hướng (Không thay đổi) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['logged_in'] = True
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('index'))
        else:
            flash('Tên đăng nhập hoặc mật khẩu không đúng!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    if session['role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('security_dashboard'))
    
# --- Các trang Admin (Không thay đổi) ---
@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    conn = get_db_connection()
    cards = conn.execute('SELECT card_id, holder_name, license_plate, ticket_type, status FROM cards ORDER BY card_id').fetchall()
    conn.close()
    return render_template('admin_dashboard.html', cards=cards)
    
@app.route('/admin/add_card', methods=['POST'])
@login_required
@role_required('admin')
def add_card():
    card_id = request.form['card_id']
    holder_name = request.form.get('holder_name', '') 
    license_plate = request.form.get('license_plate', '') 
    ticket_type = request.form.get('ticket_type', 'monthly') 

    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO cards (card_id, holder_name, license_plate, ticket_type, status) VALUES (?, ?, ?, ?, ?)',
            (card_id, holder_name, license_plate if ticket_type == 'monthly' else None, ticket_type, 'active')
        )
        conn.commit()
        flash(f'Đã thêm thẻ {card_id} thành công!', 'success')
    except sqlite3.IntegrityError:
        flash(f'Lỗi: Thẻ {card_id} đã tồn tại!', 'danger')
    finally:
        conn.close()
    return redirect(url_for('admin_dashboard'))
    
@app.route('/admin/delete_card/<card_id>')
@login_required
@role_required('admin')
def delete_card(card_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM cards WHERE card_id = ?', (card_id,))
    conn.commit()
    conn.close()
    flash(f'Đã xóa thẻ {card_id} thành công!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/transactions')
@login_required
@role_required('admin')
def view_transactions():
    conn = get_db_connection()
    rows = conn.execute(
        f"""SELECT * FROM transactions ORDER BY id DESC LIMIT 50"""
    ).fetchall()
    conn.close()
    return render_template('transactions.html', transactions=rows)
    
@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def settings():
    conn = get_db_connection()
    if request.method == 'POST':
        fee_per_hour = request.form['fee_per_hour']
        monthly_fee = request.form['monthly_fee']
        conn.execute('UPDATE settings SET value = ? WHERE key = ?', (fee_per_hour, 'fee_per_hour'))
        conn.execute('UPDATE settings SET value = ? WHERE key = ?', (monthly_fee, 'monthly_fee'))
        conn.commit()
        flash('Đã cập nhật cài đặt thành công!', 'success')
    
    settings_data = conn.execute('SELECT * FROM settings').fetchall()
    conn.close()
    settings_dict = {row['key']: row['value'] for row in settings_data}
    return render_template('settings.html', settings=settings_dict)

# ======================================================
# --- TRANG BẢO VỆ (SECURITY DASHBOARD) ---
# ======================================================

@app.route('/security/dashboard')
@login_required
@role_required('security')
def security_dashboard():
    # Trang này giờ chỉ là vỏ HTML, logic được JS xử lý qua API
    return render_template('security_dashboard.html')

# ======================================================
# --- API CHO GIAO DIỆN WEB BẢO VỆ ---
# ======================================================

@app.route('/api/gate/get_pending_scans', methods=['GET'])
@login_required
@role_required('security')
def get_pending_scans():
    """API này được dashboard của bảo vệ gọi liên tục (poll) để tìm xe (vào VÀ ra) chờ duyệt."""
    conn = get_db_connection()
    
    # Xóa các yêu cầu quá 2 phút (để tránh kẹt)
    two_min_ago = (datetime.now() - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM pending_actions WHERE status = 'pending' AND created_at < ?", (two_min_ago,))
    conn.commit()

    # Lấy yêu cầu cũ nhất
    pending = conn.execute(
        "SELECT * FROM pending_actions WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
    ).fetchone()
    
    if pending:
        # Đánh dấu là 'processing' để không bị lấy lại
        conn.execute("UPDATE pending_actions SET status = 'processing' WHERE id = ?", (pending['id'],))
        conn.commit()
        # conn.close() <-- *** LỖI NẰM Ở ĐÂY - XÓA DÒNG NÀY ***

        # Trả về một object đầy đủ, tùy thuộc vào 'entry' hay 'exit'
        if pending['action_type'] == 'entry':
            conn.close() # <-- THÊM DÒNG ĐÓNG Ở ĐÂY
            return jsonify({
                "poll_id": pending['id'],
                "action_type": "entry",
                "card_id": pending['card_id'],
                "entry_time": datetime.strptime(pending['created_at'], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M:%S")
            })
        elif pending['action_type'] == 'exit':
             # Tìm ảnh vào
            entry_snapshot = conn.execute('SELECT entry_snapshot FROM transactions WHERE id = ?', (pending['transaction_id'],)).fetchone()
            entry_snapshot_url = f"/static/snapshots/{entry_snapshot['entry_snapshot']}" if entry_snapshot and entry_snapshot['entry_snapshot'] else url_for('static', filename='placeholder.jpg')
            
            conn.close() # <-- VÀ THÊM DÒNG ĐÓNG Ở ĐÂY
            
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
                "entry_snapshot_url": entry_snapshot_url
            })
    else:
        conn.close()
        return jsonify(None) # Không có gì

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
        
        # Tạo thẻ vãng lai nếu chưa có
        card_info = conn.execute('SELECT * FROM cards WHERE card_id = ?', (card_id,)).fetchone()
        if not card_info:
             conn.execute(
                'INSERT INTO cards (card_id, holder_name, ticket_type, status) VALUES (?, ?, ?, ?)',
                (card_id, f'Khách vãng lai {license_plate}', 'daily', 'active')
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
    Đây là API DUY NHẤT mà ESP32 gọi khi quét thẻ.
    Nó xử lý cả logic VÀO và RA.
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
        
        # 2. Kiểm tra thẻ đang ở trong hay ngoài
        active_transaction = conn.execute(
            'SELECT * FROM transactions WHERE card_id = ? AND exit_time IS NULL', (card_id,)
        ).fetchone()
            
        card_info = conn.execute('SELECT * FROM cards WHERE card_id = ?', (card_id,)).fetchone()
        
        # === CASE 1: XE RA (Đã có active_transaction) ===
        if active_transaction:
            exit_time_dt = datetime.now()
            
            # Thẻ tháng ra: Miễn phí, tự động (Chụp ảnh TỪ CAM RA)
            if card_info and card_info['ticket_type'] == 'monthly':
                exit_snapshot_filename = capture_snapshot(card_id, 'out') # <-- CHỤP ẢNH CAM RA
                conn.execute(
                    'UPDATE transactions SET exit_time = ?, security_user = ?, exit_snapshot = ? WHERE id = ?',
                    (exit_time_dt.strftime("%Y-%m-%d %H:%M:%S"), 'ESP32-Gate', exit_snapshot_filename, active_transaction['id'])
                )
                conn.commit()
                conn.close()
                return jsonify({'action': 'open', 'message': 'Thẻ tháng ra. Tạm biệt!'})
            
            # Thẻ vãng lai ra: CHUYỂN SANG CHẾ ĐỘ CHỜ (POLL)
            settings_data = conn.execute('SELECT * FROM settings').fetchall()
            settings = {row['key']: row['value'] for row in settings_data}
            fee_per_hour = int(settings.get('fee_per_hour', 5000))
            
            entry_time = datetime.strptime(active_transaction['entry_time'], "%Y-%m-%d %H:%M:%S")
            duration = exit_time_dt - entry_time
            hours = max(1, -(-duration.total_seconds() // 3600)) 
            fee = int(hours * fee_per_hour)
            
            # Tạo yêu cầu 'exit'
            pending = conn.execute(
                """INSERT INTO pending_actions 
                   (card_id, status, action_type, created_at, transaction_id, license_plate, entry_time, duration, fee) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (card_id, 'pending', 'exit', exit_time_dt.strftime("%Y-%m-%d %H:%M:%S"), 
                 active_transaction['id'], active_transaction['license_plate'], active_transaction['entry_time'], 
                 str(duration).split('.')[0], fee)
            )
            conn.commit()
            poll_id = pending.lastrowid
            conn.close()
            # Yêu cầu ESP32 poll
            return jsonify({'action': 'poll', 'poll_id': poll_id, 'message': 'Xe ra, chờ bảo vệ...'})

        # === CASE 2: XE VÀO (Không có active_transaction) ===
        else:
            if not card_info:
                # Thẻ lạ, coi là vãng lai
                card_type = 'daily'
            else:
                card_type = card_info['ticket_type']

            # Thẻ tháng vào: Tự động (Chụp ảnh TỪ CAM VÀO)
            if card_type == 'monthly':
                entry_snapshot_filename = capture_snapshot(card_id, 'in') # <-- CHỤP ẢNH CAM VÀO
                conn.execute(
                    'INSERT INTO transactions (card_id, license_plate, entry_time, security_user, entry_snapshot) VALUES (?, ?, ?, ?, ?)',
                    (card_id, card_info['license_plate'], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'ESP32-Gate', entry_snapshot_filename)
                )
                conn.commit()
                conn.close()
                return jsonify({'action': 'open', 'message': 'Thẻ tháng vào. Mời vào!'})
            
            # Thẻ vãng lai vào: CHUYỂN SANG CHẾ ĐỘ CHỜ (POLL)
            else:
                # Tạo một yêu cầu trong bảng pending_actions
                pending = conn.execute(
                    "INSERT INTO pending_actions (card_id, status, action_type, created_at) VALUES (?, ?, ?, ?)",
                    (card_id, 'pending', 'entry', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                conn.commit()
                poll_id = pending.lastrowid
                conn.close()
                # Yêu cầu ESP32 poll
                return jsonify({'action': 'poll', 'poll_id': poll_id, 'message': 'Chờ bảo vệ duyệt...'})

    except Exception as e:
        if conn:
            conn.close()
        print(f"Lỗi tại /api/gate/device_scan: {e}")
        return jsonify({"action": "wait", "message": "Lỗi máy chủ nội bộ."}), 500


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
        return jsonify({"status": "denied"}) # Bị timeout hoặc hủy

    status = action['status']
    
    if status == 'approved' or status == 'denied':
        # Xóa hành động đã hoàn thành
        conn.execute("DELETE FROM pending_actions WHERE id = ?", (poll_id,))
        conn.commit()
        
    conn.close()
    return jsonify({"status": status}) # Trả về 'pending', 'approved', hoặc 'denied'


# ======================================================
# --- MỚI: API TRUYỀN VIDEO CHO WEB (ĐÃ TÁI CẤU TRÚC) ---
# ======================================================

def generate_frames(rtsp_url):
    """
    Generator đọc frame từ camera (theo rtsp_url) và trả về dưới dạng MJPEG.
    Hàm này có thể tái sử dụng cho cả camera VÀO và RA.
    """
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
                time.sleep(2) # Chờ 2 giây trước khi thử lại
                continue

            # Resize frame để giảm băng thông (TÙY CHỌN)
            frame_resized = cv2.resize(frame, (640, 480))

            # Encode thành JPEG
            (flag, encodedImage) = cv2.imencode(".jpg", frame_resized)
            if not flag:
                continue

            # Trả về frame
            yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 
                  bytearray(encodedImage) + b'\r\n')
        
        except ConnectionError as e:
            print(e)
            # Tạo frame báo lỗi
            error_frame = cv2.vconcat([cv2.vconcat([cv2.Mat(480, 640, cv2.CV_8UC3, (50, 50, 50))])])
            cv2.putText(error_frame, 'CAMERA OFFLINE', (180, 250), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            (flag, encodedImage) = cv2.imencode(".jpg", error_frame)
            if flag:
                yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 
                      bytearray(encodedImage) + b'\r\n')
            time.sleep(5) # Chờ 5 giây nếu lỗi
        
        except Exception as e:
            print(f"Lỗi không xác định trong generate_frames ({rtsp_url}): {e}")
            if cap:
                cap.release()
            cap = None
            time.sleep(5)

@app.route('/video_feed_in')
@login_required
def video_feed_in():
    """Route cho video camera VÀO."""
    return Response(generate_frames(RTSP_URL_IN),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed_out')
@login_required
def video_feed_out():
    """Route cho video camera RA."""
    return Response(generate_frames(RTSP_URL_OUT),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


# --- Chạy ứng dụng ---
if __name__ == '__main__':
    # Chạy trên tất cả IP, debug=False để OpenCV chạy ổn định trên nhiều thread
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)