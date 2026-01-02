from flask import Flask

from admin_routes import register_admin_routes
from auth import register_auth_routes
from core import SECRET_KEY, register_filters
from security_routes import register_security_routes


def create_app():
    app = Flask(__name__)
    app.secret_key = SECRET_KEY

    register_filters(app)
    register_auth_routes(app)
    register_admin_routes(app)
    register_security_routes(app)
    return app


app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
