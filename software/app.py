# --- Import các thư viện cần thiết ---
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash, Response
import sqlite3
import os
import json
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
# Lưu ý: Thay đổi URL này phù hợp với camera thực tế của bạn
RTSP_URL_IN = "rtsp://admin:admin@192.168.0.101:8554/live"
RTSP_URL_OUT = "rtsp://admin:admin@192.168.0.103:8554/live"

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
# def capture_snapshot(card_id, event_type):
#     """
#     Kết nối đến RTSP, chụp một khung hình và lưu lại.
#     Trả về tên file nếu thành công, hoặc tên file placeholder nếu thất bại.
#     """
#     placeholder_filename = "placeholder.jpg" # Tên file dự phòng
    
#     # === THAY ĐỔI: Chọn đúng URL camera ===
#     if event_type == 'in':
#         rtsp_url = RTSP_URL_IN
#         print(f"Chụp ảnh VÀO từ: {rtsp_url}")
#     elif event_type == 'out':
#         rtsp_url = RTSP_URL_OUT
#         print(f"Chụp ảnh RA từ: {rtsp_url}")
#     else:
#         rtsp_url = RTSP_URL_IN # Mặc định
#     # ======================================
    
#     cap = None
#     try:
#         # 1. Kết nối đến camera
#         cap = cv2.VideoCapture(rtsp_url)
        
#         # Thử đọc 5 khung hình đầu để xóa bộ đệm (buffer)
#         for _ in range(5):
#             cap.read()
            
#         ret, frame = cap.read() # Đọc khung hình chính
        
#         if not ret or frame is None:
#             print(f"Lỗi: Không thể đọc frame từ camera RTSP: {rtsp_url}")
#             raise Exception("Không thể đọc frame")

#         # 2. Tạo tên file và đường dẫn
#         timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
#         filename = f"{card_id}_{timestamp}_{event_type}.jpg"
#         destination_path = os.path.join(SNAPSHOT_DIR, filename)

#         # 3. Lưu ảnh
#         cv2.imwrite(destination_path, frame)
#         print(f"Đã lưu ảnh chụp: {filename}")
#         return filename

#     except Exception as e:
#         print(f"Lỗi khi chụp ảnh từ {rtsp_url}: {e}. Sử dụng ảnh placeholder.")
#         # Nếu có lỗi, copy ảnh placeholder
#         placeholder_path_src = os.path.join(BASE_DIR, 'static', placeholder_filename)
#         if not os.path.exists(placeholder_path_src):
#             try:
#                 # Tạo placeholder nếu chưa có
#                 img = cv2.vconcat([cv2.vconcat([cv2.Mat(100, 300, cv2.CV_8UC3, (128, 128, 128))])])
#                 cv2.putText(img, 'CAMERA OFFLINE', (50, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
#                 cv2.imwrite(placeholder_path_src, img)
#             except: pass # Bỏ qua nếu không tạo được
        
#         # Copy file placeholder đến đúng vị trí
#         timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
#         filename = f"{card_id}_{timestamp}_{event_type}_offline.jpg"
#         destination_path = os.path.join(SNAPSHOT_DIR, filename)
#         try:
#             shutil.copy(placeholder_path_src, destination_path)
#         except:
#              return placeholder_filename # Trả về placeholder gốc
#         return filename # Trả về file placeholder đã copy

#     finally:
#         # 4. Luôn giải phóng camera
#         if cap:
#             cap.release()

def capture_snapshot(card_id, event_type):
    """
    PHIÊN BẢN TEST PHẦN CỨNG:
    Hàm này bỏ qua việc kết nối Camera RTSP để tránh bị Lag/Timeout.
    Nó sẽ copy ảnh placeholder.jpg có sẵn thành ảnh chụp mới.
    """
    print(f"--- [TEST MODE] Bỏ qua Camera, tạo ảnh giả lập cho thẻ {card_id} ---")
    
    placeholder_filename = "placeholder.jpg"
    
    # Tạo tên file mới dựa trên thời gian
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{card_id}_{timestamp}_{event_type}_offline.jpg"
    
    # Đường dẫn nguồn (ảnh mẫu) và đích (ảnh lưu)
    placeholder_path_src = os.path.join(BASE_DIR, 'static', placeholder_filename)
    destination_path = os.path.join(SNAPSHOT_DIR, filename)
    
    try:
        # Kiểm tra nếu chưa có ảnh mẫu thì tạo ra một cái (phòng hờ)
        if not os.path.exists(placeholder_path_src):
            try:
                # Tạo ảnh màu xám đơn giản bằng OpenCV
                img = cv2.Mat(100, 300, cv2.CV_8UC3, (128, 128, 128))
                cv2.putText(img, 'NO CAMERA', (50, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.imwrite(placeholder_path_src, img)
            except: 
                pass # Bỏ qua nếu không cài opencv hoặc lỗi tạo ảnh
            
        # Copy ảnh mẫu sang thư mục snapshots
        shutil.copy(placeholder_path_src, destination_path)
        return filename
        
    except Exception as e:
        print(f"Lỗi khi tạo ảnh giả lập: {e}")
        return placeholder_filename # Trả về ảnh gốc nếu lỗi

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
            if user['status'] == 'locked':
                flash('Tài khoản này đã bị KHÓA. Vui lòng liên hệ Admin.', 'danger')
                return render_template('login.html')
            
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

# ======================================================
# --- QUẢN LÝ NHÂN VIÊN (USER MANAGEMENT) ---
# ======================================================

@app.route('/admin/users')
@login_required
@role_required('admin')
def user_management():
    conn = get_db_connection()
    users = conn.execute('SELECT username, role, status FROM users').fetchall()
    conn.close()
    return render_template('user_management.html', users=users)

@app.route('/admin/users/add', methods=['POST'])
@login_required
@role_required('admin')
def add_user():
    username = request.form['username'].strip()
    password = request.form['password']
    role = request.form['role']
    status = request.form.get('status', 'active') 
    
    if not username or not password:
        flash('Vui lòng nhập đầy đủ thông tin!', 'danger')
        return redirect(url_for('user_management'))

    hashed_password = generate_password_hash(password)
    
    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO users (username, password_hash, role, status) VALUES (?, ?, ?, ?)',
            (username, hashed_password, role, status)
        )
        conn.commit()
        flash(f'Đã thêm nhân viên "{username}" thành công!', 'success')
    except sqlite3.IntegrityError:
        flash(f'Lỗi: Tên đăng nhập "{username}" đã tồn tại!', 'danger')
    finally:
        conn.close()
    return redirect(url_for('user_management'))

@app.route('/admin/users/delete/<username>')
@login_required
@role_required('admin')
def delete_user(username):
    if username == session['username']:
        flash('Bạn không thể xóa tài khoản đang đăng nhập!', 'danger')
        return redirect(url_for('user_management'))

    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE username = ?', (username,))
    conn.commit()
    conn.close()
    flash(f'Đã xóa nhân viên "{username}"!', 'success')
    return redirect(url_for('user_management'))

@app.route('/admin/users/toggle_status/<username>')
@login_required
@role_required('admin')
def toggle_user_status(username):
    if username == session['username']:
        flash('Không thể tự khóa chính mình!', 'danger')
        return redirect(url_for('user_management'))

    conn = get_db_connection()
    user = conn.execute('SELECT status FROM users WHERE username = ?', (username,)).fetchone()
    
    if user:
        new_status = 'locked' if user['status'] == 'active' else 'active'
        conn.execute('UPDATE users SET status = ? WHERE username = ?', (new_status, username))
        conn.commit()
        msg = 'Đã KHÓA' if new_status == 'locked' else 'Đã MỞ KHÓA'
        flash(f'{msg} tài khoản "{username}"!', 'success')
    
    conn.close()
    return redirect(url_for('user_management'))

@app.route('/admin/users/reset_password', methods=['POST'])
@login_required
@role_required('admin')
def reset_password():
    username = request.form['username']
    new_password = request.form['new_password']
    
    if not new_password:
        flash('Mật khẩu mới không được để trống!', 'danger')
        return redirect(url_for('user_management'))

    hashed_password = generate_password_hash(new_password)
    
    conn = get_db_connection()
    conn.execute(
        'UPDATE users SET password_hash = ? WHERE username = ?',
        (hashed_password, username)
    )
    conn.commit()
    conn.close()
    flash(f'Đã đổi mật khẩu cho "{username}" thành công!', 'success')
    return redirect(url_for('user_management'))
###
    
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

@app.route('/admin/statistics')
@login_required
@role_required('admin')
def statistics():
    conn = get_db_connection()
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    revenue_today = conn.execute(
        "SELECT SUM(fee) FROM transactions WHERE date(exit_time) = ? AND fee IS NOT NULL", 
        (today_str,)
    ).fetchone()[0] or 0

    traffic_today = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE date(entry_time) = ?", 
        (today_str,)
    ).fetchone()[0] or 0

    cars_in_parking = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE exit_time IS NULL"
    ).fetchone()[0] or 0

    filter_type = request.args.get('filter', '7days') 
    start_input = request.args.get('start', '')
    end_input = request.args.get('end', '')

    end_date = datetime.now()
    start_date = end_date - timedelta(days=6) 

    if filter_type == '6months':
        start_date = end_date - timedelta(days=180)
    elif filter_type == 'custom' and start_input and end_input:
        try:
            start_date = datetime.strptime(start_input, "%Y-%m-%d")
            end_date = datetime.strptime(end_input, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            pass 

    date_labels = []
    delta = (end_date - start_date).days
    if delta < 0: delta = 0
    
    for i in range(delta + 1):
        day = start_date + timedelta(days=i)
        date_labels.append(day.strftime("%Y-%m-%d"))

    s_str = start_date.strftime("%Y-%m-%d 00:00:00")
    e_str = end_date.strftime("%Y-%m-%d 23:59:59")

    rev_data = conn.execute("""
        SELECT date(exit_time) as day, SUM(fee) as total 
        FROM transactions 
        WHERE exit_time BETWEEN ? AND ? AND fee IS NOT NULL
        GROUP BY date(exit_time)
    """, (s_str, e_str)).fetchall()
    
    traf_data = conn.execute("""
        SELECT date(entry_time) as day, COUNT(*) as total 
        FROM transactions 
        WHERE entry_time BETWEEN ? AND ?
        GROUP BY date(entry_time)
    """, (s_str, e_str)).fetchall()
    
    conn.close()

    rev_dict = {row['day']: row['total'] for row in rev_data}
    traf_dict = {row['day']: row['total'] for row in traf_data}

    final_dates = []   
    final_revenues = []
    final_traffics = []

    for d_str in date_labels:
        d_obj = datetime.strptime(d_str, "%Y-%m-%d")
        final_dates.append(d_obj.strftime("%d/%m"))
        
        final_revenues.append(rev_dict.get(d_str, 0))
        final_traffics.append(traf_dict.get(d_str, 0))

    return render_template('statistics.html', 
                           revenue_today=revenue_today,
                           traffic_today=traffic_today,
                           cars_in_parking=cars_in_parking,
                           dates=json.dumps(final_dates),
                           revenues=json.dumps(final_revenues),
                           traffics=json.dumps(final_traffics),
                           current_filter=filter_type,
                           current_start=start_date.strftime("%Y-%m-%d"),
                           current_end=end_date.strftime("%Y-%m-%d"))

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
    conn.execute("DELETE FROM pending_actions WHERE status IN ('pending', 'alert_unregistered') AND created_at < ?", (two_min_ago,))
    conn.commit()

    # 2. Lấy yêu cầu mới nhất (bao gồm cả 'pending' VÀ 'alert_unregistered')
    pending = conn.execute(
        "SELECT * FROM pending_actions WHERE status IN ('pending', 'alert_unregistered') ORDER BY created_at ASC LIMIT 1"
    ).fetchone()
    
    if pending:
        # === TRƯỜNG HỢP 1: CẢNH BÁO THẺ LẠ ===
        if pending['status'] == 'alert_unregistered':
            # Xóa ngay bản ghi này để không báo lại liên tục
            conn.execute("DELETE FROM pending_actions WHERE id = ?", (pending['id'],))
            conn.commit()
            conn.close()
            
            # Trả về JSON đặc biệt loại 'alert'
            return jsonify({
                "action_type": "alert",
                "card_id": pending['card_id'],
                "message": f"CẢNH BÁO: Phát hiện thẻ lạ {pending['card_id']}!"
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
                "entry_snapshot_url": entry_snapshot_url
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

            # Tính phí (Chỉ tính nếu là vé ngày - daily)
            fee = 0
            if card_type == 'daily':
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)