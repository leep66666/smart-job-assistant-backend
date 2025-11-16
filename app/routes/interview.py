# app/routes/interview.py
import logging
from typing import Optional

from flask import Blueprint, jsonify, request, url_for

from ..config import Config
from ..services.files import (
    ensure_dirs,
    ext_ok,
    read_text_from_file,
    save_file,
    truncate_text,
)
from ..services.interview_service import (
    AnswerRecord,
    build_report,
    create_session,
    get_session,
    submit_answer,
)

bp = Blueprint("interview", __name__)
logger = logging.getLogger(__name__)


def _extract_job_description() -> tuple[Optional[str], list[str]]:
    """
    Optionally receive a JD file, store it for reference and return text content.
    """
    jd_file = request.files.get("jobDescription")
    if not jd_file:
        return None, []
    if not ext_ok(jd_file.filename):
        raise ValueError("Unsupported job description file type")

    ensure_dirs()
    jd_path = save_file(jd_file, Config.JD_DIR)  # type: ignore[name-defined]
    text, warn = read_text_from_file(jd_path)
    text, wcut = truncate_text(text, Config.MAX_INPUT_CHARS)
    warnings = [w for w in (warn, wcut) if w]
    return text, warnings


@bp.post("/api/interview/questions")
def api_interview_questions():
    """
    创建新的面试 session，根据职位描述使用模型生成面试问题。
    """
    warnings: list[str] = []
    job_text: Optional[str] = None

    try:
        job_text, jd_warnings = _extract_job_description()
        warnings.extend(jd_warnings)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - 保底
        logger.exception("处理 JD 文件失败")
        return jsonify({"success": False, "message": f"解析职位描述失败: {exc}"}), 500

    session = create_session(job_text)
    
    # 添加问题生成的警告信息
    question_warnings = session.info.get("questionGenerationWarnings", [])
    if question_warnings:
        warnings.extend(question_warnings)
    
    questions_payload = [
        {
            "id": question.id,
            "text": question.text,
            "durationSeconds": question.duration_seconds,
        }
        for question in session.questions
    ]

    return jsonify(
        {
            "success": True,
            "sessionId": session.session_id,
            "questions": questions_payload,
            "currentQuestionId": session.questions[0].id if session.questions else None,
            "warnings": warnings,
        }
    ), 200


@bp.post("/api/interview/answer")
def api_interview_answer():
    session_id = request.form.get("sessionId")
    question_id = request.form.get("questionId")
    if not session_id or not question_id:
        return jsonify({"success": False, "message": "Missing sessionId or questionId"}), 400

    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"success": False, "message": "Audio file is required."}), 400

    elapsed_raw = request.form.get("elapsedSeconds")
    elapsed_seconds: Optional[float] = None
    if elapsed_raw:
        try:
            elapsed_seconds = float(elapsed_raw)
        except ValueError:
            return jsonify({"success": False, "message": "Invalid elapsedSeconds value."}), 400

    try:
        record, next_question_id, next_question_text, warnings = submit_answer(
            session_id=session_id,
            question_id=question_id,
            audio_file=audio_file,
            elapsed_seconds=elapsed_seconds,
        )
    except KeyError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - 防御性
        logger.exception("处理面试回答失败")
        return jsonify({"success": False, "message": f"提交回答失败: {exc}"}), 500

    response_payload = _serialize_answer(record, warnings, next_question_id, next_question_text)
    return jsonify({"success": True, **response_payload}), 200


def _serialize_answer(
    record: AnswerRecord,
    warnings: list[str],
    next_question_id: Optional[str],
    next_question_text: Optional[str],
) -> dict:
    payload = {
        "questionId": record.question_id,
        "transcript": record.transcript,
        "evaluation": record.evaluation,
        "durationSeconds": record.duration_seconds,
        "nextQuestionId": next_question_id,
        "nextQuestionText": next_question_text,
        "hasMoreQuestions": next_question_id is not None,
        "warnings": warnings,
    }
    return payload


@bp.get("/api/interview/report/<session_id>")
def api_interview_report(session_id: str):
    try:
        report, markdown = build_report(session_id)
    except KeyError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except Exception as exc:  # pragma: no cover
        logger.exception("生成面试报告失败")
        return jsonify({"success": False, "message": f"生成报告失败: {exc}"}), 500

    download_url = url_for("uploads.download_file", file_name=report["downloadName"], _external=True)
    return jsonify(
        {
            "success": True,
            "report": report,
            "markdown": markdown,
            "downloadUrl": download_url,
        }
    ), 200


@bp.get("/api/interview/session/<session_id>")
def api_interview_session(session_id: str):
    try:
        session = get_session(session_id)
    except KeyError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404

    next_question_id = (
        session.questions[session.current_index].id
        if session.current_index < len(session.questions)
        else None
    )
    return jsonify(
        {
            "success": True,
            "sessionId": session.session_id,
            "currentIndex": session.current_index,
            "questionCount": len(session.questions),
            "nextQuestionId": next_question_id,
        }
    ), 200
