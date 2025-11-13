import logging
from flask import Flask
from flask_cors import CORS
from .config import Config
from .services.files import ensure_dirs
from .routes.resume import bp as resume_bp
from .routes.interview import bp as interview_bp
from .routes.uploads import bp as uploads_bp

def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # logging
    logging.basicConfig(level=Config.LOG_LEVEL,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    # CORS
    CORS(app, resources={r"/api/*": {"origins": Config.CORS_ORIGINS}})

    # 上传目录就绪
    ensure_dirs()

    # 注册路由
    app.register_blueprint(resume_bp)
    app.register_blueprint(interview_bp)
    app.register_blueprint(uploads_bp)

    return app