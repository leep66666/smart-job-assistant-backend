# app/routes/resume.py
import os
import re
import uuid
import shutil
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Iterable, Tuple

from flask import Blueprint, request, jsonify, url_for
from openai import OpenAI

from app.config import Config
from app.services.files import (
    ensure_dirs, ext_ok, save_file,
    read_text_from_file, truncate_text,
)
from app.services.prompts import build_resume_prompt

bp = Blueprint("resume", __name__)
logger = logging.getLogger(__name__)

# 初始化qwen
QWEN_API_KEY = "" #用之前写自己的qwen api
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url=QWEN_BASE_URL,
)


# Markdown -> LaTeX
TRIPLE_BACKTICK_RE = re.compile(r"^\s*```(?:[a-zA-Z]+)?\s*([\s\S]*?)\s*```\s*$")

LATEX_SPECIAL = {
    '\\': r'\textbackslash{}',
    '{': r'\{',
    '}': r'\}',
    '#': r'\#',
    '$': r'\$',
    '%': r'\%',
    '&': r'\&',
    '_': r'\_',
    '^': r'\^{}',
    '~': r'\~{}',
}

def strip_code_fences(text: str) -> str:
    """去掉最外层 ``` 包裹（若存在），返回内部内容。"""
    m = TRIPLE_BACKTICK_RE.match(text.strip())
    if m:
        return m.group(1).strip()
    return text.strip()

def escape_latex(text: str) -> str:
    """转义普通段落中的 LaTeX 特殊字符"""
    text = text.replace('\\', LATEX_SPECIAL['\\'])
    for ch, rep in LATEX_SPECIAL.items():
        if ch == '\\':
            continue
        text = text.replace(ch, rep)
    return text

def markdown_to_latex(md: str) -> str:
    """
    极简 Markdown -> LaTeX：
    - #/##/### -> \section/\subsection/\subsubsection
    - 列表行以 -, *, • 开头 -> itemize
    - 行内 `code` -> \texttt{}
    - 三引号代码块 ``` -> verbatim
    - 其他行做 LaTeX 特殊字符转义
    """
    import re
    lines = md.splitlines()
    out = []
    in_verbatim = False
    in_itemize = False

    def flush_itemize():
        nonlocal in_itemize
        if in_itemize:
            out.append(r'\end{itemize}')
            in_itemize = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # ``` 代码块
        if re.match(r'\s*```', line):
            flush_itemize()
            if not in_verbatim:
                out.append(r'\begin{verbatim}')
                in_verbatim = True
            else:
                out.append(r'\end{verbatim}')
                in_verbatim = False
            i += 1
            continue

        if in_verbatim:
            out.append(line)  # verbatim 内不转义
            i += 1
            continue

        # 标题
        if line.startswith('### '):
            flush_itemize()
            out.append(r'\subsubsection{' + escape_latex(line[4:].strip()) + '}')
            i += 1
            continue
        if line.startswith('## '):
            flush_itemize()
            out.append(r'\subsection{' + escape_latex(line[3:].strip()) + '}')
            i += 1
            continue
        if line.startswith('# '):
            flush_itemize()
            out.append(r'\section{' + escape_latex(line[2:].strip()) + '}')
            i += 1
            continue

        # 列表项
        if re.match(r'^\s*([-*•])\s+', line):
            if not in_itemize:
                out.append(r'\begin{itemize}')
                in_itemize = True
            item_text = re.sub(r'^\s*([-*•])\s+', '', line)
            out.append(r'\item ' + escape_latex(item_text))
            i += 1
            continue
        else:
            flush_itemize()

        # 行内代码
        def repl_inline_code(m):
            inner = m.group(1)
            inner = inner.replace('\\', r'\textbackslash{}').replace('{', r'\{').replace('}', r'\}')
            return r'\texttt{' + inner + '}'

        line = re.sub(r'`([^`]+)`', repl_inline_code, line)

        # 普通段落
        out.append(escape_latex(line) if line.strip() else '')
        i += 1

    flush_itemize()
    return '\n'.join(out)

def wrap_into_template(body: str, chinese: bool = True) -> str:
    """
    支持中文字体
    """
    if chinese:
        return r"""
\documentclass[11pt]{article}
\usepackage{fontspec}
\setmainfont{Times New Roman}
\newfontfamily\cnfont{PingFang SC}
\usepackage{geometry}
\geometry{a4paper,margin=1in}
\usepackage[colorlinks=true,linkcolor=blue,urlcolor=blue]{hyperref}
\setlength{\parskip}{6pt}
\begin{document}
{\cnfont
""" + body + r"""
}
\end{document}
"""
    else:
        return r"""
\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{geometry}
\geometry{a4paper,margin=1in}
\usepackage[colorlinks=true,linkcolor=blue,urlcolor=blue]{hyperref}
\setlength{\parskip}{6pt}
\begin{document}
""" + body + r"""
\end{document}
"""
# LaTeX 编译

def compile_latex_to_pdf(tex_content: str, file_id: str, timeout_sec: int = 300) -> Tuple[str, str, str]:
    """
    写入 .tex，调用 tectonic（优先）或 pdflatex 编译 pdf。失败抛出详细错误。
    返回: (final_tex_path, final_pdf_path, file_id)
    """
    ensure_dirs()
    upload_dir = Path(getattr(Config, "UPLOAD_DIR", getattr(Config, "OUTPUT_DIR", "uploads")))
    upload_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        tex_path = tmpdir_path / f"{file_id}.tex"
        pdf_path_tmp = tmpdir_path / f"{file_id}.pdf"

        tex_path.write_text(tex_content, encoding="utf-8")

        tectonic_bin = shutil.which("tectonic")
        if tectonic_bin:
            cmd = [tectonic_bin, "--keep-logs", "--keep-intermediates", str(tex_path)]
            logger.info(f"Running tectonic: {' '.join(cmd)}")
            try:
                proc = subprocess.run(
                    cmd, cwd=tmpdir_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, timeout=timeout_sec
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"LaTeX 编译超过 {timeout_sec}s 超时（可能在下载宏包/字体或被某宏包阻塞）。")
            if proc.returncode != 0 or not pdf_path_tmp.exists():
                raise RuntimeError(f"tectonic 编译失败：\n{proc.stdout}")
        else:
            pdflatex_bin = shutil.which("pdflatex")
            if not pdflatex_bin:
                raise RuntimeError("找不到 LaTeX 编译器：请安装 'tectonic' 或 'pdflatex'（TeX Live/MacTeX）。")
            cmd = [pdflatex_bin, "-interaction=nonstopmode", tex_path.name]
            try:
                logger.info(f"Running pdflatex: {' '.join(cmd)} (1/2)")
                p1 = subprocess.run(cmd, cwd=tmpdir_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout_sec)
                logger.info(f"Running pdflatex: {' '.join(cmd)} (2/2)")
                p2 = subprocess.run(cmd, cwd=tmpdir_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"LaTeX 编译超过 {timeout_sec}s 超时。")
            if p2.returncode != 0 or not pdf_path_tmp.exists():
                log = (p1.stdout or "") + "\n" + (p2.stdout or "")
                raise RuntimeError(f"pdflatex 编译失败：\n{log}")

        # 移动到可下载目录
        final_tex = upload_dir / f"{file_id}.tex"
        final_pdf = upload_dir / f"{file_id}.pdf"
        shutil.move(str(tex_path), str(final_tex))
        shutil.move(str(pdf_path_tmp), str(final_pdf))

    return str(final_tex), str(final_pdf), file_id

def gen_file_id(prefix: str = "resume") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# 主要 API：生成简历（Qwen Markdown -> LaTeX -> PDF）
@bp.post("/api/resume/generate")
def api_resume_generate():
    """
    输入：上传的 resume / jobDescription 文件
    流程：Qwen 生成 Markdown -> 本地转安全 LaTeX -> (尝试) 编译 PDF
    返回：始终包含 generatedResume；PDF 成功则给 downloadPdf，失败则仅返回 MD 并附警告
    """
    ensure_dirs()

    resume = request.files.get("resume")
    jd = request.files.get("jobDescription")
    if not resume or not jd:
        return jsonify({"success": False, "message": "Both files are required."}), 400
    if not ext_ok(resume.filename) or not ext_ok(jd.filename):
        return jsonify({"success": False, "message": "Unsupported file type"}), 400

    # 保存原始文件
    resume_path = save_file(resume, Config.RESUME_DIR)
    jd_path = save_file(jd, Config.JD_DIR)

    # 读取文本
    resume_text, w1 = read_text_from_file(resume_path)
    jd_text, w2 = read_text_from_file(jd_path)
    warnings = [w for w in (w1, w2) if w]

    # 截断（可配置）
    resume_text, w3 = truncate_text(resume_text, Config.MAX_INPUT_CHARS)
    jd_text, w4 = truncate_text(jd_text, Config.MAX_INPUT_CHARS)
    warnings.extend([w for w in (w3, w4) if w])

    # 组装 Prompt
    base_prompt = build_resume_prompt(resume_text, jd_text)

    # 统一 fileId，后续 .md/.tex/.pdf 用同一个前缀
    file_id = gen_file_id()

    # 强约束：让 Qwen 输出 Markdown（便于前端渲染/备份）
    system_prompt = (
        "You are a professional resume writer. "
        "Return a SINGLE GitHub-flavored Markdown document ONLY (no LaTeX math). "
        "Do NOT wrap the entire output in code fences. "
        "Use clear section headings (e.g., # Summary, ## Experience, ## Education, ## Skills). "
        "Avoid raw special characters like %, _, &, $, ^, ~ unless in code blocks. "
        "Keep it one page when converted to PDF. English headings allowed; content may include Chinese."
    )

    try:
        # 1) 调用 Qwen 生成 Markdown
        completion = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": base_prompt},
            ],
            temperature=0.3,
        )

        raw_md = completion.choices[0].message.content or ""
        generated_md = strip_code_fences(raw_md)  # ← 这个就是前端要的 generatedResume

        # 2) 先把 Markdown 存成 .md，生成下载链接
        upload_dir = Path(getattr(Config, "UPLOAD_DIR", getattr(Config, "OUTPUT_DIR", "uploads")))
        upload_dir.mkdir(parents=True, exist_ok=True)
        md_path = upload_dir / f"{file_id}.md"
        md_path.write_text(generated_md, encoding="utf-8")
        download_md = url_for("uploads.download_file", file_name=f"{file_id}.md", _external=True)

        # 3) 尝试生成 PDF（失败不影响主流程）
        download_pdf = None
        try:
            # Markdown -> LaTeX
            latex_body = markdown_to_latex(generated_md)
            # 选择是否中文模板：纯英文可改为 chinese=False
            latex_text = wrap_into_template(latex_body, chinese=True)

            tex_path, pdf_path, _ = compile_latex_to_pdf(latex_text, file_id)
            download_pdf = url_for("uploads.download_file", file_name=f"{file_id}.pdf", _external=True)
        except Exception as latex_err:
            warnings.append(f"PDF generation skipped: {latex_err}")

        # 4) 返回：务必包含 generatedResume，前端才能切换到结果页
        return jsonify({
            "success": True,
            "generatedResume": generated_md,
            "fileId": file_id,
            "downloadMd": download_md,
            "downloadPdf": download_pdf,   # 可能为 None
            "resumeSaved": resume_path,
            "jdSaved": jd_path,
            "warnings": warnings,
        }), 200

    except Exception as e:
        logger.exception("调用 Qwen API / LaTeX 编译失败")
        return jsonify({"success": False, "message": f"生成失败: {e}"}), 500