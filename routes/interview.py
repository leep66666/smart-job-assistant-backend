# app/routes/interview.py
import json
import logging
from flask import Blueprint, request, jsonify

from ..config import Config                      # ← 这里改为 Config
from ..services.files import (                   # 保持与之前一致
    ensure_dirs, ext_ok, save_file,
    read_text_from_file, truncate_text
)
from ..services.prompts import build_questions_prompt
from ..services.llm import run_ollama

bp = Blueprint("interview", __name__)
logger = logging.getLogger(__name__)

@bp.post("/api/interview/questions")
def api_interview_questions():
    ensure_dirs()

    jd = request.files.get("jobDescription")
    if not jd:
        return jsonify({"success": False, "message": "JobDescription file is required."}), 400
    if not ext_ok(jd.filename):
        return jsonify({"success": False, "message": "Unsupported file type"}), 400

    jd_path = save_file(jd, Config.JD_DIR)
    jd_text, warn = read_text_from_file(jd_path)
    jd_text, wcut = truncate_text(jd_text, Config.MAX_INPUT_CHARS)
    warnings = [w for w in (warn, wcut) if w]

    prompt = build_questions_prompt(jd_text)
    try:
        raw = run_ollama(prompt, stream=False).strip()
        try:
            questions = json.loads(raw)
            assert isinstance(questions, list)
        except Exception:
            lines = [x.strip("- ").strip() for x in raw.splitlines() if x.strip()]
            questions = [{"question": ln, "followups": []} for ln in lines][:12]

        return jsonify({
            "success": True,
            "questions": questions,
            "savedPath": jd_path,
            "warnings": warnings
        }), 200

    except Exception as e:
        logger.exception("生成面试问题失败")
        return jsonify({"success": False, "message": f"生成失败: {e}"}), 500