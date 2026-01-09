import os

from flask import Flask

from config import Config
from app.routes import admin_bp, api_bp, auth_bp, security_bp
from app.utils import register_template_filters


def create_app(config_class=Config):
    app = Flask(__name__, template_folder="templates", static_folder="../static")
    app.config.from_object(config_class)

    os.makedirs(app.config["SNAPSHOT_DIR"], exist_ok=True)
    register_template_filters(app)
    _register_blueprints(app)
    return app


def _register_blueprints(app: Flask):
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(api_bp)
    _alias_legacy_endpoints(app)


def _alias_legacy_endpoints(app: Flask):
    """
    Giữ nguyên tên endpoint cũ (không có prefix blueprint) để không phải sửa HTML/JS hiện có.
    """
    mapping = {
        "auth.index": "index",
        "auth.login": "login",
        "auth.logout": "logout",
        "admin.admin_dashboard": "admin_dashboard",
        "admin.user_management": "user_management",
        "admin.add_user": "add_user",
        "admin.delete_user": "delete_user",
        "admin.toggle_user_status": "toggle_user_status",
        "admin.reset_password": "reset_password",
        "admin.add_card": "add_card",
        "admin.edit_card": "edit_card",
        "admin.set_card_status": "set_card_status",
        "admin.delete_card": "delete_card",
        "admin.view_transactions": "view_transactions",
        "admin.settings": "settings",
        "admin.statistics": "statistics",
        "security.security_dashboard": "security_dashboard",
        "security.get_pending_scans": "get_pending_scans",
        "security.confirm_pending_entry": "confirm_pending_entry",
        "security.cancel_pending_action": "cancel_pending_action",
        "security.confirm_pending_exit": "confirm_pending_exit",
        "api.device_scan": "device_scan",
        "api.check_action_status": "check_action_status",
        "api.video_feed_in": "video_feed_in",
        "api.video_feed_out": "video_feed_out",
    }

    for source, alias in mapping.items():
        if alias in app.view_functions:
            continue
        view_func = app.view_functions.get(source)
        if not view_func:
            continue

        rules = list(app.url_map.iter_rules(source))
        for rule in rules:
            methods = [m for m in rule.methods if m not in {"HEAD", "OPTIONS"}]
            app.add_url_rule(
                rule.rule,
                endpoint=alias,
                view_func=view_func,
                defaults=rule.defaults,
                methods=methods or None,
            )
            # Đưa alias lên đầu danh sách rule để request.endpoint khớp alias cũ.
            new_rule = app.url_map._rules.pop()
            app.url_map._rules.insert(0, new_rule)
