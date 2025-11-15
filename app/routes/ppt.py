# app/routes/ppt.py
import os
import logging
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename

from app.config import Config
from app.services.files import ext_ok, save_file, read_text_from_file, truncate_text
from app.services.ppt_service import generate_self_intro_ppt

bp = Blueprint("ppt", __name__)
logger = logging.getLogger(__name__)


@bp.post("/api/ppt/generate")
def generate_ppt():
    """生成自我介绍PPT"""
    try:
        # 检查文件上传
        if 'resume' not in request.files:
            return jsonify({
                "success": False,
                "message": "请上传简历文件"
            }), 400
        
        if 'jobDescription' not in request.files:
            return jsonify({
                "success": False,
                "message": "请上传岗位JD文件"
            }), 400
        
        resume_file = request.files['resume']
        jd_file = request.files['jobDescription']
        
        # 验证文件
        if resume_file.filename == '' or not ext_ok(resume_file.filename):
            return jsonify({
                "success": False,
                "message": "简历文件格式不支持，请上传PDF、Word或TXT文件"
            }), 400
        
        if jd_file.filename == '' or not ext_ok(jd_file.filename):
            return jsonify({
                "success": False,
                "message": "岗位JD文件格式不支持，请上传PDF、Word或TXT文件"
            }), 400
        
        # 保存文件
        resume_path = save_file(resume_file, Config.RESUME_DIR)
        jd_path = save_file(jd_file, Config.JD_DIR)
        
        logger.info(f"简历文件已保存: {resume_path}")
        logger.info(f"JD文件已保存: {jd_path}")
        
        # 读取文件内容
        resume_text, resume_warn = read_text_from_file(resume_path)
        jd_text, jd_warn = read_text_from_file(jd_path)
        
        warnings = []
        if resume_warn:
            warnings.append(f"简历文件: {resume_warn}")
        if jd_warn:
            warnings.append(f"JD文件: {jd_warn}")
        
        if not resume_text:
            return jsonify({
                "success": False,
                "message": "无法读取简历文件内容"
            }), 400
        
        if not jd_text:
            return jsonify({
                "success": False,
                "message": "无法读取岗位JD文件内容"
            }), 400
        
        # 截断文本（如果需要）
        resume_text, resume_trunc_warn = truncate_text(resume_text, Config.MAX_INPUT_CHARS)
        jd_text, jd_trunc_warn = truncate_text(jd_text, Config.MAX_INPUT_CHARS)
        
        if resume_trunc_warn:
            warnings.append(f"简历: {resume_trunc_warn}")
        if jd_trunc_warn:
            warnings.append(f"JD: {jd_trunc_warn}")
        
        # 生成PPT
        ppt_path, error = generate_self_intro_ppt(
            resume_text, 
            jd_text, 
            Config.OUTPUT_DIR
        )
        
        if error:
            logger.error(f"生成PPT失败: {error}")
            return jsonify({
                "success": False,
                "message": f"生成PPT失败: {error}"
            }), 500
        
        # 获取文件名
        ppt_filename = os.path.basename(ppt_path)
        
        logger.info(f"PPT生成成功: {ppt_path}")
        
        # 直接使用相对路径，避免url_for可能的问题
        download_url = f"/api/files/{ppt_filename}"
        
        return jsonify({
            "success": True,
            "message": "PPT生成成功",
            "downloadUrl": download_url,
            "filename": ppt_filename,
            "warnings": warnings if warnings else None
        }), 200
        
    except Exception as e:
        logger.error(f"生成PPT时出错: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": f"服务器错误: {str(e)}"
        }), 500

