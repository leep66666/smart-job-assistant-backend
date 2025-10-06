import os
from flask import Blueprint, jsonify, send_file
from app.config import Config
from app.services.api import list_ollama_models, ping_ollama

bp = Blueprint("uploads", __name__)

@bp.get("/health")
def health():
    try:
        ping_ollama()
        return jsonify({"ok": True, "model": Config.OLLAMA_MODEL})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@bp.get("/api/models")
def models():
    try:
        return jsonify({"success": True, "models": list_ollama_models()})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@bp.get("/api/files/<file_name>")
def download_file(file_name: str):
    path = os.path.join(Config.OUTPUT_DIR, file_name)
    if not os.path.isfile(path):
        return jsonify({"success": False, "message": "file not found"}), 404
    return send_file(path, as_attachment=True, download_name=file_name)