import json
import sqlite3
from datetime import datetime, timedelta

from flask import render_template, request, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash

from auth import login_required, role_required
from core import (
    get_db_connection,
    escape_like,
    parse_int_param,
    add_months,
    generate_next_employee_code,
)


def register_admin_routes(app):
    # --- Các trang Admin (Không thay đổi) ---
    @app.route('/admin/dashboard')
    @login_required
    @role_required('admin')
    def admin_dashboard():
        q = (request.args.get('q') or '').strip()
        ticket_type = (request.args.get('ticket_type') or '').strip()
        status_filter = (request.args.get('status') or '').strip()
        page = parse_int_param(request.args.get('page', 1), 1)
        per_page = parse_int_param(request.args.get('per_page', 25), 25, 100)
        offset = (page - 1) * per_page

        conn = get_db_connection()
        conditions = []
        params = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if q:
            like_term = f"%{escape_like(q)}%"
            conditions.append(
                "(card_id LIKE ? ESCAPE '\\' OR IFNULL(holder_name,'') LIKE ? ESCAPE '\\' OR IFNULL(license_plate,'') LIKE ? ESCAPE '\\')"
            )
            params.extend([like_term, like_term, like_term])

        if ticket_type in ('monthly', 'daily'):
            conditions.append("ticket_type = ?")
            params.append(ticket_type)

        if status_filter == 'expired':
            conditions.append("ticket_type = 'monthly' AND expiry_date IS NOT NULL AND expiry_date < ?")
            params.append(now_str)
        elif status_filter in ('active', 'lost'):
            conditions.append("status = ?")
            params.append(status_filter)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        total_cards = conn.execute(f"SELECT COUNT(*) FROM cards {where_clause}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT card_id, holder_name, license_plate, ticket_type, status, created_at, expiry_date
                FROM cards
                {where_clause}
                ORDER BY created_at DESC, card_id
                LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        ).fetchall()
        conn.close()

        cards = []
        now_dt = datetime.now()
        for row in rows:
            card = dict(row)
            is_expired = False
            if card.get('expiry_date'):
                try:
                    is_expired = datetime.strptime(card['expiry_date'], "%Y-%m-%d %H:%M:%S") < now_dt
                except ValueError:
                    is_expired = False
            display_status = card.get('status') or 'unknown'
            if display_status != 'lost' and card.get('ticket_type') == 'monthly' and is_expired:
                display_status = 'expired'
            card['display_status'] = display_status
            cards.append(card)

        has_next = offset + per_page < total_cards
        prev_url = url_for('admin_dashboard', **{k: v for k, v in {
            'q': q or None,
            'ticket_type': ticket_type or None,
            'status': status_filter or None,
            'per_page': per_page,
            'page': page - 1
        }.items() if v is not None}) if page > 1 else None
        next_url = url_for('admin_dashboard', **{k: v for k, v in {
            'q': q or None,
            'ticket_type': ticket_type or None,
            'status': status_filter or None,
            'per_page': per_page,
            'page': page + 1
        }.items() if v is not None}) if has_next else None

        return render_template(
            'admin_dashboard.html',
            cards=cards,
            page=page,
            per_page=per_page,
            total_cards=total_cards,
            filters={
                'q': q,
                'ticket_type': ticket_type,
                'status': status_filter,
            },
            prev_url=prev_url,
            next_url=next_url
        )

    # ======================================================
    # --- QUẢN LÝ NHÂN VIÊN (USER MANAGEMENT) ---
    # ======================================================

    @app.route('/admin/users')
    @login_required
    @role_required('admin')
    def user_management():
        q = (request.args.get('q') or '').strip()
        role_filter = (request.args.get('role') or '').strip()
        status_filter = (request.args.get('status') or '').strip()
        page = parse_int_param(request.args.get('page', 1), 1)
        per_page = parse_int_param(request.args.get('per_page', 25), 25, 100)
        offset = (page - 1) * per_page

        conn = get_db_connection()
        conditions = []
        params = []

        if q:
            like_term = f"%{escape_like(q)}%"
            conditions.append(
                "(username LIKE ? ESCAPE '\\' OR full_name LIKE ? ESCAPE '\\' OR employee_code LIKE ? ESCAPE '\\')"
            )
            params.extend([like_term, like_term, like_term])

        if role_filter in ('admin', 'security'):
            conditions.append("role = ?")
            params.append(role_filter)

        if status_filter in ('active', 'locked'):
            conditions.append("status = ?")
            params.append(status_filter)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        total_users = conn.execute(f"SELECT COUNT(*) FROM users {where_clause}", params).fetchone()[0]
        users = conn.execute(
            f"""SELECT username, role, status, employee_code, full_name
                FROM users
                {where_clause}
                ORDER BY employee_code
                LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        ).fetchall()
        conn.close()

        has_next = offset + per_page < total_users
        prev_url = url_for('user_management', **{k: v for k, v in {
            'q': q or None,
            'role': role_filter or None,
            'status': status_filter or None,
            'per_page': per_page,
            'page': page - 1
        }.items() if v is not None}) if page > 1 else None
        next_url = url_for('user_management', **{k: v for k, v in {
            'q': q or None,
            'role': role_filter or None,
            'status': status_filter or None,
            'per_page': per_page,
            'page': page + 1
        }.items() if v is not None}) if has_next else None

        return render_template(
            'user_management.html',
            users=users,
            page=page,
            per_page=per_page,
            total_users=total_users,
            filters={
                'q': q,
                'role': role_filter,
                'status': status_filter,
            },
            prev_url=prev_url,
            next_url=next_url
        )

    @app.route('/admin/users/add', methods=['POST'])
    @login_required
    @role_required('admin')
    def add_user():
        username = request.form['username'].strip()
        password = request.form['password']
        role = request.form['role']
        status = request.form.get('status', 'active') 
        full_name = (request.form.get('full_name', '') or '').strip()
        
        if not username or not password or not full_name:
            flash('Vui lòng nhập đầy đủ thông tin (họ tên, tài khoản, mật khẩu)!', 'danger')
            return redirect(url_for('user_management'))

        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            employee_code = generate_next_employee_code(conn)
            conn.execute(
                'INSERT INTO users (username, password_hash, role, status, employee_code, full_name) VALUES (?, ?, ?, ?, ?, ?)',
                (username, hashed_password, role, status, employee_code, full_name)
            )
            conn.commit()
            flash(f'Đã thêm nhân viên "{full_name}" (Mã {employee_code}) thành công!', 'success')
        except ValueError as exc:
            conn.rollback()
            flash(str(exc), 'danger')
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            error_msg = str(exc)
            if 'users.username' in error_msg:
                flash(f'Lỗi: Tên đăng nhập "{username}" đã tồn tại!', 'danger')
            elif 'employee_code' in error_msg:
                flash('Lỗi: Mã nhân viên bị trùng, vui lòng thử lại.', 'danger')
            else:
                flash('Không thể thêm nhân viên, vui lòng thử lại.', 'danger')
        finally:
            conn.close()
        return redirect(url_for('user_management'))

    @app.route('/admin/users/delete/<username>')
    @login_required
    @role_required('admin')
    def delete_user(username):
        flash('Hệ thống không hỗ trợ xóa tài khoản nhân viên. Vui lòng khóa thay vì xóa.', 'warning')
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
        card_id = request.form['card_id'].strip()
        holder_name = (request.form.get('holder_name', '') or '').strip()
        license_plate = (request.form.get('license_plate', '') or '').strip()
        ticket_type = request.form.get('ticket_type', 'monthly')

        if not card_id:
            flash('ID thẻ không được để trống!', 'danger')
            return redirect(url_for('admin_dashboard'))

        if ticket_type == 'monthly':
            if not holder_name or not license_plate:
                flash('Vé tháng cần Tên chủ thẻ và Biển số xe.', 'danger')
                return redirect(url_for('admin_dashboard'))

        created_at_dt = datetime.now()
        created_at = created_at_dt.strftime("%Y-%m-%d %H:%M:%S")
        expiry_date = None
        if ticket_type == 'monthly':
            expiry_date = add_months(created_at_dt, 1).strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db_connection()
        try:
            conn.execute(
                'INSERT INTO cards (card_id, holder_name, license_plate, ticket_type, expiry_date, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (card_id, holder_name if ticket_type == 'monthly' else 'N/A',
                 license_plate if ticket_type == 'monthly' else None, ticket_type, expiry_date, created_at, 'active')
            )
            conn.commit()
            flash(f'Đã thêm thẻ {card_id} thành công!', 'success')
        except sqlite3.IntegrityError:
            flash(f'ID thẻ {card_id} đã tồn tại, vui lòng kiểm tra để xóa ID cũ hoặc dùng ID khác.', 'danger')
        finally:
            conn.close()
        return redirect(url_for('admin_dashboard'))

    @app.route('/admin/edit_card', methods=['POST'])
    @login_required
    @role_required('admin')
    def edit_card():
        original_card_id = request.form['original_card_id']
        new_card_id = request.form['card_id'].strip()
        holder_name = request.form.get('holder_name', '').strip()
        license_plate = (request.form.get('license_plate', '') or '').strip() or None
        extend_months = int(request.form.get('extend_months', 0) or 0)

        if not new_card_id:
            flash('ID thẻ không được để trống!', 'danger')
            return redirect(url_for('admin_dashboard'))

        conn = get_db_connection()
        try:
            card = conn.execute('SELECT * FROM cards WHERE card_id = ?', (original_card_id,)).fetchone()
            if not card:
                flash('Không tìm thấy thẻ cần chỉnh sửa.', 'danger')
                return redirect(url_for('admin_dashboard'))

            ticket_type = card['ticket_type']
            base_date_str = card['expiry_date'] or card['created_at']
            new_expiry_date = card['expiry_date']

            if ticket_type == 'monthly' and extend_months > 0:
                try:
                    base_date = datetime.strptime(base_date_str, "%Y-%m-%d %H:%M:%S") if base_date_str else datetime.now()
                except ValueError:
                    base_date = datetime.now()

                new_expiry_dt = add_months(base_date, extend_months)
                new_expiry_date = new_expiry_dt.strftime("%Y-%m-%d %H:%M:%S")

                settings_data = conn.execute('SELECT * FROM settings').fetchall()
                settings = {row['key']: row['value'] for row in settings_data}
                monthly_fee = int(settings.get('monthly_fee', 0))
                total_amount = monthly_fee * extend_months
                paid_at = datetime.now()
                month_label = paid_at.strftime("%Y-%m")
                conn.execute(
                    "INSERT INTO monthly_payments (card_id, month, amount, paid_at) VALUES (?, ?, ?, ?)",
                    (new_card_id, month_label, total_amount, paid_at.strftime("%Y-%m-%d %H:%M:%S"))
                )

            conn.execute(
                """UPDATE cards 
                   SET card_id = ?, holder_name = ?, license_plate = ?, expiry_date = ?
                   WHERE card_id = ?""",
                (new_card_id, holder_name, license_plate if ticket_type == 'monthly' else None, new_expiry_date, original_card_id)
            )
            conn.commit()
            flash(f'Đã cập nhật thẻ {new_card_id} thành công!', 'success')
        except sqlite3.IntegrityError:
            conn.rollback()
            flash('ID thẻ mới đã tồn tại, vui lòng chọn ID khác.', 'danger')
        except Exception as e:
            conn.rollback()
            flash(f'Lỗi khi cập nhật thẻ: {e}', 'danger')
        finally:
            conn.close()
        return redirect(url_for('admin_dashboard'))

    @app.route('/admin/cards/set_status', methods=['POST'])
    @login_required
    @role_required('admin')
    def set_card_status():
        card_id = (request.form.get('card_id') or '').strip()
        new_status = request.form.get('status')

        if not card_id or new_status not in ('active', 'lost'):
            flash('Yêu cầu đổi trạng thái không hợp lệ.', 'danger')
            return redirect(url_for('admin_dashboard'))

        conn = get_db_connection()
        try:
            card = conn.execute('SELECT * FROM cards WHERE card_id = ?', (card_id,)).fetchone()
            if not card:
                flash('Không tìm thấy thẻ cần cập nhật trạng thái.', 'danger')
                return redirect(url_for('admin_dashboard'))

            conn.execute('UPDATE cards SET status = ? WHERE card_id = ?', (new_status, card_id))
            conn.commit()
            msg = 'Đã kích hoạt lại thẻ.' if new_status == 'active' else 'Đã báo mất thẻ, thẻ bị vô hiệu hóa.'
            flash(msg, 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Lỗi khi cập nhật trạng thái thẻ: {e}', 'danger')
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
        q = (request.args.get('q') or '').strip()
        status_filter = (request.args.get('status') or '').strip()
        guard_filter = (request.args.get('guard') or '').strip()
        date_from = (request.args.get('from') or '').strip()
        date_to = (request.args.get('to') or '').strip()
        page = parse_int_param(request.args.get('page', 1), 1)
        per_page = parse_int_param(request.args.get('per_page', 25), 25, 200)
        offset = (page - 1) * per_page

        conn = get_db_connection()
        conditions = []
        params = []

        if q:
            like_term = f"%{escape_like(q)}%"
            conditions.append(
                "(card_id LIKE ? ESCAPE '\\' OR IFNULL(license_plate,'') LIKE ? ESCAPE '\\' OR IFNULL(security_user,'') LIKE ? ESCAPE '\\')"
            )
            params.extend([like_term, like_term, like_term])

        if status_filter == 'open':
            conditions.append("exit_time IS NULL")
        elif status_filter == 'closed':
            conditions.append("exit_time IS NOT NULL")

        if guard_filter:
            like_guard = f"%{escape_like(guard_filter)}%"
            conditions.append("IFNULL(security_user,'') LIKE ? ESCAPE '\\'")
            params.append(like_guard)

        if date_from:
            conditions.append("exit_time IS NOT NULL AND exit_time >= ?")
            params.append(f"{date_from} 00:00:00")
        if date_to:
            conditions.append("exit_time IS NOT NULL AND exit_time <= ?")
            params.append(f"{date_to} 23:59:59")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        total_transactions = conn.execute(f"SELECT COUNT(*) FROM transactions {where_clause}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT * FROM transactions
                {where_clause}
                ORDER BY id DESC
                LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        ).fetchall()
        conn.close()

        has_next = offset + per_page < total_transactions
        prev_url = url_for('view_transactions', **{k: v for k, v in {
            'q': q or None,
            'status': status_filter or None,
            'guard': guard_filter or None,
            'from': date_from or None,
            'to': date_to or None,
            'per_page': per_page,
            'page': page - 1
        }.items() if v is not None}) if page > 1 else None
        next_url = url_for('view_transactions', **{k: v for k, v in {
            'q': q or None,
            'status': status_filter or None,
            'guard': guard_filter or None,
            'from': date_from or None,
            'to': date_to or None,
            'per_page': per_page,
            'page': page + 1
        }.items() if v is not None}) if has_next else None

        return render_template(
            'transactions.html',
            transactions=rows,
            page=page,
            per_page=per_page,
            total_transactions=total_transactions,
            filters={
                'q': q,
                'status': status_filter,
                'guard': guard_filter,
                'from': date_from,
                'to': date_to,
            },
            prev_url=prev_url,
            next_url=next_url
        )
        
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

        active_tab = request.args.get('active_tab', 'walkin')

        # === Thống kê vãng lai (theo ngày) ===
        walkin_filter = request.args.get('filter_daily', '7days') 
        start_input = request.args.get('start_daily', '')
        end_input = request.args.get('end_daily', '')

        end_date = datetime.now()
        start_date = end_date - timedelta(days=6) 

        if walkin_filter == '6months':
            start_date = end_date - timedelta(days=180)
        elif walkin_filter == 'custom' and start_input and end_input:
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

        # === Thống kê vé tháng (theo tháng) ===
        def shift_month(base_dt, offset):
            year = base_dt.year + (base_dt.month - 1 + offset) // 12
            month = (base_dt.month - 1 + offset) % 12 + 1
            return base_dt.replace(year=year, month=month, day=1)

        month_filter = request.args.get('filter_monthly', '6months')
        start_month_input = request.args.get('start_month', '')
        end_month_input = request.args.get('end_month', '')

        month_end = datetime.now().replace(day=1)
        month_start = shift_month(month_end, -5)

        if month_filter == '12months':
            month_start = shift_month(month_end, -11)
        elif month_filter == 'custom' and start_month_input and end_month_input:
            try:
                month_start = datetime.strptime(start_month_input, "%Y-%m").replace(day=1)
                month_end = datetime.strptime(end_month_input, "%Y-%m").replace(day=1)
                if month_start > month_end:
                    month_start, month_end = month_end, month_start
            except ValueError:
                pass

        monthly_dates = []
        cursor_month = month_start
        while cursor_month <= month_end:
            monthly_dates.append(cursor_month)
            next_month = cursor_month.replace(day=28) + timedelta(days=4)
            cursor_month = next_month.replace(day=1)

        month_keys = [m.strftime("%Y-%m") for m in monthly_dates]
        month_labels = [m.strftime("%m/%Y") for m in monthly_dates]

        if month_keys:
            m_start_key = month_keys[0]
            m_end_key = month_keys[-1]
        else:
            m_start_key = month_end.strftime("%Y-%m")
            m_end_key = month_end.strftime("%Y-%m")

        conn_month = get_db_connection()
        monthly_rev_data = conn_month.execute("""
            SELECT month, SUM(amount) as total
            FROM monthly_payments
            WHERE month BETWEEN ? AND ?
            GROUP BY month
            ORDER BY month
        """, (m_start_key, m_end_key)).fetchall()

        monthly_count_data = conn_month.execute("""
            SELECT month, COUNT(*) as total
            FROM monthly_payments
            WHERE month BETWEEN ? AND ?
            GROUP BY month
            ORDER BY month
        """, (m_start_key, m_end_key)).fetchall()
        conn_month.close()

        monthly_rev_dict = {row['month']: row['total'] for row in monthly_rev_data}
        monthly_count_dict = {row['month']: row['total'] for row in monthly_count_data}

        monthly_revenues = [monthly_rev_dict.get(key, 0) for key in month_keys]
        monthly_counts = [monthly_count_dict.get(key, 0) for key in month_keys]
        monthly_total = sum(monthly_revenues)
        monthly_payment_count = sum(monthly_counts)

        return render_template('statistics.html', 
                               revenue_today=revenue_today,
                               traffic_today=traffic_today,
                               cars_in_parking=cars_in_parking,
                               dates=json.dumps(final_dates),
                               revenues=json.dumps(final_revenues),
                               traffics=json.dumps(final_traffics),
                               current_filter=walkin_filter,
                               current_start=start_date.strftime("%Y-%m-%d"),
                               current_end=end_date.strftime("%Y-%m-%d"),
                               monthly_labels=json.dumps(month_labels),
                               monthly_revenues=json.dumps(monthly_revenues),
                               monthly_counts=json.dumps(monthly_counts),
                               monthly_filter=month_filter,
                               monthly_start=month_start.strftime("%Y-%m"),
                               monthly_end=month_end.strftime("%Y-%m"),
                               monthly_total=monthly_total,
                               monthly_payment_count=monthly_payment_count,
                               active_tab=active_tab)
