import os
from flask import Blueprint, jsonify, send_file
from app.config import Config

bp = Blueprint("uploads", __name__)

@bp.get("/health")
def health():
    """健康检查端点，不再依赖ollama"""
    return jsonify({"ok": True, "message": "Service is running"})

@bp.get("/api/models")
def models():
    """模型列表端点，已切换到Qwen API"""
    return jsonify({
        "success": True, 
        "models": ["qwen-plus"],
        "message": "Using Qwen API"
    })

@bp.get("/api/files/<file_name>")
def download_file(file_name: str):
    from pathlib import Path
    
    # 获取项目根目录（app 目录的父目录）
    app_dir = Path(__file__).parent.parent
    base_dir = app_dir.parent if app_dir.name == "app" else app_dir
    
    # 构建绝对路径
    candidates = [
        base_dir / Config.OUTPUT_DIR / file_name,
        base_dir / Config.INTERVIEW_REPORT_DIR / file_name,
        # 兼容旧路径
        Path(Config.OUTPUT_DIR) / file_name,
        Path(Config.INTERVIEW_REPORT_DIR) / file_name,
    ]
    
    for path in candidates:
        path_abs = path.resolve() if isinstance(path, Path) else Path(path).resolve()
        if path_abs.is_file():
            return send_file(str(path_abs), as_attachment=True, download_name=file_name)
    
    return jsonify({"success": False, "message": f"file not found: {file_name}"}), 404