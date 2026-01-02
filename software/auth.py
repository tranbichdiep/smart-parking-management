from functools import wraps
from flask import render_template, request, session, redirect, url_for, flash
from werkzeug.security import check_password_hash

from core import get_db_connection


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


def register_auth_routes(app):
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
