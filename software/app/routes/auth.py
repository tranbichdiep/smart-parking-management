from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from app.database import get_db_connection
from app.utils import login_required

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            if user["status"] == "locked":
                flash("Tài khoản này đã bị KHÓA. Vui lòng liên hệ Admin.", "danger")
                return render_template("login.html")

            session["logged_in"] = True
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("auth.index"))
        flash("Tên đăng nhập hoặc mật khẩu không đúng!", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/")
@login_required
def index():
    if session["role"] == "admin":
        return redirect(url_for("admin.admin_dashboard"))
    return redirect(url_for("security.security_dashboard"))
