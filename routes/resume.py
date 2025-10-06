import json
from flask import Blueprint, request, jsonify, url_for
from app.config import Config
from app.services.files import (
    ensure_dirs, ext_ok, save_file,
    read_text_from_file, truncate_text, write_outputs
)
from app.services.prompts import build_resume_prompt
from app.services.llm import run_ollama
import logging

bp = Blueprint("resume", __name__)
logger = logging.getLogger(__name__)

@bp.post("/api/resume/generate")
def api_resume_generate():
    ensure_dirs()

    resume = request.files.get("resume")
    jd = request.files.get("jobDescription")
    if not resume or not jd:
        return jsonify({"success": False, "message": "Both files are required."}), 400
    if not ext_ok(resume.filename) or not ext_ok(jd.filename):
        return jsonify({"success": False, "message": "Unsupported file type"}), 400

    resume_path = save_file(resume, Config.RESUME_DIR)
    jd_path = save_file(jd, Config.JD_DIR)

    resume_text, w1 = read_text_from_file(resume_path)
    jd_text, w2 = read_text_from_file(jd_path)
    warnings = [w for w in (w1, w2) if w]

    resume_text, w3 = truncate_text(resume_text, Config.MAX_INPUT_CHARS)
    jd_text, w4 = truncate_text(jd_text, Config.MAX_INPUT_CHARS)
    warnings.extend([w for w in (w3, w4) if w])

    prompt = build_resume_prompt(resume_text, jd_text)

    try:
        generated_md = run_ollama(prompt, stream=False)
        md_path, pdf_path, file_id = write_outputs(generated_md)

        download_md = url_for("uploads.download_file", file_name=file_id + ".md", _external=True)
        download_pdf = url_for("uploads.download_file", file_name=file_id + ".pdf", _external=True)

        return jsonify({
            "success": True,
            "generatedResume": generated_md,
            "fileId": file_id,
            "downloadMd": download_md,
            "downloadPdf": download_pdf,
            "resumeSaved": resume_path,
            "jdSaved": jd_path,
            "warnings": warnings,
        }), 200

    except Exception as e:
        logger.exception("调用 ollama 失败")
        return jsonify({"success": False, "message": f"生成失败: {e}"}), 500