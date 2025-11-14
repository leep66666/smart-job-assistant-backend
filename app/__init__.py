import logging
from flask import Flask
from flask_cors import CORS

from .config import Config
from .services.files import ensure_dirs
from .routes.resume import bp as resume_bp
from .routes.interview import bp as interview_bp
from .routes.uploads import bp as uploads_bp

# 👇 新增：引入全局 db 实例
from .extensions import db


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # 👇 新增：初始化 SQLAlchemy（一定要在使用 db 前调用）
    db.init_app(app)

    # logging
    logging.basicConfig(
        level=Config.LOG_LEVEL,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    # CORS
    CORS(app, resources={r"/api/*": {"origins": Config.CORS_ORIGINS}})

    # 上传目录就绪
    ensure_dirs()

    # 注册路由 / 蓝图
    app.register_blueprint(resume_bp)
    app.register_blueprint(interview_bp)
    app.register_blueprint(uploads_bp)

    # 👇 新增：在应用上下文中创建表（开发环境用这个就够了）
    with app.app_context():
        # 确保模型被导入，让 SQLAlchemy 知道这些表
        from app.models import ResumeUser, ResumeGeneration  # 还有其他模型也可以一起导
        db.create_all()

    return app