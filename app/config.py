# app/config.py
import os

class Config:
    """
    全局配置对象：通过 app.config.from_object(Config) 加载。
    仅包含原 test 程序用到的配置项，不引入新功能。
    """

    # ===== 路径与上传目录 =====
    UPLOAD_ROOT = os.environ.get("UPLOAD_ROOT", "./uploads")
    RESUME_DIR  = os.path.join(UPLOAD_ROOT, "resumes")
    JD_DIR      = os.path.join(UPLOAD_ROOT, "job_descriptions")
    OUTPUT_DIR  = os.path.join(UPLOAD_ROOT, "outputs")
    INTERVIEW_ROOT = os.path.join(UPLOAD_ROOT, "interview")
    INTERVIEW_AUDIO_DIR = os.path.join(INTERVIEW_ROOT, "audio")
    INTERVIEW_REPORT_DIR = os.path.join(INTERVIEW_ROOT, "reports")

    # ===== 日志与请求大小限制 =====
    LOG_LEVEL  = os.environ.get("LOG_LEVEL", "INFO").upper()
    MAX_MB     = int(os.environ.get("MAX_UPLOAD_MB", "10"))
    # Flask 识别的内容长度限制（单位：字节）
    MAX_CONTENT_LENGTH = MAX_MB * 1024 * 1024

    # ===== 数据库配置（新增） =====
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "mysql+pymysql://root:Hku123456@localhost:3306/smart_job_assistant?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ===== CORS 白名单（与原 app.py 保持一致）=====
    CORS_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # ===== 模型与推理参数（与原 app.py 完全一致）=====
    OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "qwen:7b")
    GEN_TEMPERATURE = float(os.environ.get("GEN_TEMPERATURE", "0.2"))
    MAX_INPUT_CHARS = int(os.environ.get("MAX_INPUT_CHARS", "24000"))

    # ===== 允许的扩展名（与原 app.py 完全一致）=====
    ALLOWED_EXTS = {".pdf", ".docx", ".txt"}

    # ===== 讯飞实时转写配置 =====
    # 必须通过环境变量设置，不允许硬编码
    XFYUN_APPID = os.environ.get("XFYUN_APPID", "")
    XFYUN_API_KEY = os.environ.get("XFYUN_API_KEY", "")