# app/routes/resume.py
import os
import re
import uuid
import shutil
import logging
import tempfile
import subprocess
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

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
# 优先使用 DASHSCOPE_API_KEY（百炼API Key），从环境变量读取，不允许硬编码
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

def get_qwen_client():
    """
    延迟初始化 OpenAI 客户端，每次调用时重新读取环境变量
    这样可以确保在 .env.local 加载后也能正确获取 API key
    """
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY", "")
    if not api_key:
        logger.warning("DASHSCOPE_API_KEY 或 QWEN_API_KEY 未设置，简历生成功能将无法正常工作。请设置环境变量 DASHSCOPE_API_KEY 或 QWEN_API_KEY")
    else:
        logger.info(f"API Key 已配置（长度: {len(api_key)}）")
    return OpenAI(
        api_key=api_key,
        base_url=QWEN_BASE_URL,
    )

# Markdown -> LaTeX
TRIPLE_BACKTICK_RE = re.compile(r"^\s*```(?:[a-zA-Z]+)?\s*([\s\S]*?)\s*```\s*$")


def detect_language(text: str) -> str:
    """
    检测文本的主要语言（中文或英文）
    返回 'zh' 或 'en'
    """
    if not text:
        return 'en'  # 默认英文

    # 统计中文字符数量
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total_chars = len(re.findall(r'[a-zA-Z\u4e00-\u9fff]', text))

    if total_chars == 0:
        return 'en'

    # 如果中文字符占比超过30%，认为是中文
    if chinese_chars / total_chars > 0.3:
        return 'zh'
    return 'en'


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


def manual_resume_to_text(payload: Dict[str, Any]) -> str:
    """
    把前端传来的 manualResume JSON（ManualResumeFormData）转成一段纯文本，
    作为“原始简历内容”喂给大模型。
    """
    if not isinstance(payload, dict):
        return ""

    lines = []

    personal = payload.get("personal") or {}
    personal_parts = [
        personal.get("fullName"),
        personal.get("email"),
        personal.get("phoneCode"),
        personal.get("phoneNumber"),
    ]
    personal_text = " ".join(filter(None, personal_parts)).strip()
    if personal_text:
        lines.append(f"Personal Information: {personal_text}")

    def join_section(title: str, entries):
        section_lines = []
        for item in entries or []:
            if not isinstance(item, dict):
                continue
            values = [str(v).strip() for v in item.values() if isinstance(v, str) and v.strip()]
            if values:
                section_lines.append(f"- {'; '.join(values)}")
        if section_lines:
            lines.append(f"{title}:\n" + "\n".join(section_lines))

    join_section("Education", payload.get("education"))
    join_section("Internships", payload.get("internships"))
    join_section("Work Experience", payload.get("work"))
    join_section("Projects", payload.get("projects"))

    skills = payload.get("skills") or {}
    skills_values = [skills.get("programming"), skills.get("office"), skills.get("languages")]
    skills_text = "; ".join(filter(None, skills_values))
    if skills_text:
        lines.append(f"Skills: {skills_text}")

    join_section("Competitions", payload.get("competitions"))

    return "\n".join(line for line in lines if line).strip()


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
    改进的 Markdown -> LaTeX 转换：
    - # 姓名 -> 大标题居中显示
    - ## 章节 -> \section
    - ### 子章节 -> \subsection
    - 列表行以 -, *, • 开头 -> itemize (使用 enumitem 改进格式)
    - 行内 `code` -> \texttt{}
    - **bold** -> \textbf{}
    - *italic* -> \textit{}
    - [text](url) -> \href{url}{text}
    - 三引号代码块 ``` -> verbatim
    - 防止长文本溢出
    """
    import re
    lines = md.splitlines()
    out = []
    in_verbatim = False
    in_itemize = False
    in_minipage = False  # 跟踪是否在minipage环境中
    is_first_line = True  # 标记第一行（姓名）

    def flush_itemize(check_next=True):
        nonlocal in_itemize, in_minipage
        if in_itemize:
            out.append(r'\end{itemize}')
            in_itemize = False
            # 如果列表结束且下一行不是列表项，关闭minipage
            if in_minipage and check_next and i < len(lines):
                next_line = lines[i].strip() if i < len(lines) else ""
                if not next_line or next_line.startswith('#') or re.match(r'^\s*\*\*', next_line):
                    out.append(r'\end{minipage}')
                    in_minipage = False

    def process_inline_formatting(text: str) -> str:
        """处理行内格式：粗体、斜体、代码、链接，并修复符号前后空白"""
        placeholders = {}
        placeholder_counter = [0]

        def get_placeholder():
            placeholder_counter[0] += 1
            return f"PLACEHOLDER{placeholder_counter[0]}PLACEHOLDER"

        # inline code
        def repl_inline_code(m):
            placeholder = get_placeholder()
            inner = m.group(1)
            inner = inner.replace('\\', r'\textbackslash{}').replace('{', r'\{').replace('}', r'\}')
            placeholders[placeholder] = r'\texttt{' + inner + '}'
            return placeholder

        text = re.sub(r'`([^`]+)`', repl_inline_code, text)

        # links
        def repl_link(m):
            placeholder = get_placeholder()
            link_text = m.group(1)
            link_url = m.group(2)
            link_url_escaped = (
                link_url.replace('\\', r'\textbackslash{}')
                .replace('{', r'\{').replace('}', r'\}')
                .replace('#', r'\#').replace('$', r'\$').replace('%', r'\%')
                .replace('&', r'\&').replace('_', r'\_').replace('^', r'\^{}')
                .replace('~', r'\~{}')
            )
            placeholders[placeholder] = r'\href{' + link_url_escaped + '}{' + escape_latex(link_text) + '}'
            return placeholder

        text = re.sub(r'$begin:math:display$\(\[\^$end:math:display$]+\]$begin:math:text$\(\[\^$end:math:text$]+\)', repl_link, text)

        # bold
        def repl_bold(m):
            placeholder = get_placeholder()
            placeholders[placeholder] = r'\textbf{' + escape_latex(m.group(1)) + '}'
            return placeholder

        text = re.sub(r'\*\*([^\*]+)\*\*', repl_bold, text)
        text = re.sub(r'__([^_]+)__', repl_bold, text)

        # italic
        def repl_italic(m):
            placeholder = get_placeholder()
            placeholders[placeholder] = r'\textit{' + escape_latex(m.group(1)) + '}'
            return placeholder

        text = re.sub(r'(?<!\*)\*([^\*]+)\*(?!\*)', repl_italic, text)
        text = re.sub(r'(?<!_)_([^_]+)_(?!_)', repl_italic, text)

        # 修复符号前后的空白
        text = re.sub(r'([^\s~\-])\s+\+\s+([^\s~\-])', r'\1~+~\2', text)
        text = re.sub(r'([^\s~\-])\s+-\s+([^\s~\-])', r'\1~-~\2', text)
        text = re.sub(r'([^\s~])\s+=\s+([^\s~])', r'\1~=~\2', text)
        text = re.sub(r'([^\s~])\s+<\s+([^\s~])', r'\1~<~\2', text)
        text = re.sub(r'([^\s~])\s+>\s+([^\s~])', r'\1~>~\2', text)

        text = escape_latex(text)

        for placeholder, replacement in placeholders.items():
            text = text.replace(placeholder, replacement)

        return text

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
            out.append(line)
            i += 1
            continue

        # 标题处理
        if line.startswith('### '):
            flush_itemize()
            title_text = process_inline_formatting(line[4:].strip())
            out.append(r'\subsubsection{' + title_text + '}')
            i += 1
            continue
        if line.startswith('## '):
            flush_itemize()
            title_text = process_inline_formatting(line[3:].strip())
            out.append(r'\section{' + title_text + '}')
            i += 1
            continue
        if line.startswith('# '):
            flush_itemize()
            title_text = process_inline_formatting(line[2:].strip())
            if is_first_line:
                out.append(r'\begin{tabularx}{\linewidth}{@{} C @{}}')
                out.append(r'\Huge{' + title_text + r'} \\[7.5pt]')
                is_first_line = False
                i += 1
                # 下一行如果是联系方式
                if i < len(lines) and lines[i].strip() and not lines[i].startswith('#'):
                    contact_line = lines[i].strip()
                    contact_parts = [p.strip() for p in contact_line.split('|')]
                    contact_latex = []
                    for part in contact_parts:
                        part_processed = process_inline_formatting(part)
                        contact_latex.append(part_processed)
                    contact_text = r' \ $|$ \ '.join(contact_latex)
                    out.append(contact_text + r' \\')
                    i += 1
                out.append(r'\end{tabularx}')
                continue
            else:
                out.append(r'\section{' + title_text + '}')
                i += 1
                continue

        # 列表项
        list_match = re.match(r'^\s*([-*•])\s+', line)
        if list_match:
            if not in_itemize:
                if out and out[-1].strip().endswith(r'\end{tabularx}'):
                    out.append(r'\begin{minipage}[t]{\linewidth}')
                    in_minipage = True
                out.append(r'\begin{itemize}[nosep,after=\strut, leftmargin=1em, itemsep=3pt,label=--]')
                in_itemize = True
            item_text = re.sub(r'^\s*([-*•])\s+', '', line)
            item_text = process_inline_formatting(item_text)
            out.append(r'\item ' + item_text)
            i += 1
            continue
        else:
            flush_itemize()

        # 空行
        if not line.strip():
            out.append('')
            i += 1
            continue

        # 工作经历/项目标题
        job_match = re.match(r'^\s*\*\*([^\*]+)\*\*\s*$begin:math:text$\(\[\^$end:math:text$]+\)', line)
        if job_match:
            flush_itemize()
            job_title = job_match.group(1).strip()
            job_time = job_match.group(2).strip()
            out.append(r'\begin{tabularx}{\linewidth}{@{}l X r@{}}')
            out.append(
                r'\textbf{' + escape_latex(job_title) + r'} & \hfill & ' + escape_latex(job_time) + r' \\[3.75pt]')
            out.append(r'\end{tabularx}')
            i += 1
            continue

        # 普通段落
        processed_line = process_inline_formatting(line)
        out.append(processed_line)
        i += 1

    flush_itemize(check_next=False)
    if in_minipage:
        out.append(r'\end{minipage}')
    return '\n'.join(out)


def wrap_into_template(body: str, chinese: bool = True) -> str:
    """
    使用改进的 LaTeX 模板，参考专业简历格式，防止内容溢出
    """
    preamble = r"""
\documentclass[a4paper,12pt]{article}
\usepackage{url}
\usepackage{parskip}
\RequirePackage{color}
\RequirePackage{graphicx}
\usepackage[usenames,dvipsnames]{xcolor}
\usepackage[scale=0.9]{geometry}
\usepackage{tabularx}
\usepackage{enumitem}
\usepackage{supertabular}
\usepackage{titlesec}
\usepackage{multicol}
\usepackage{multirow}
"""

    if chinese:
        preamble += r"""
\usepackage{fontspec}
% 设置中文字体为默认字体
\setmainfont{PingFang SC}[Ligatures=TeX]
\newfontfamily\cnfont{PingFang SC}
"""
    else:
        preamble += r"""
\usepackage[T1]{fontenc}
\usepackage{lmodern}
"""

    preamble += r"""
% 自定义章节格式
"""
    if chinese:
        preamble += r"""
\titleformat{\section}{\Large\bfseries\raggedright}{}{0em}{}[\titlerule]
\titlespacing{\section}{0pt}{10pt}{10pt}
"""
    else:
        preamble += r"""
\titleformat{\section}{\Large\scshape\raggedright}{}{0em}{}[\titlerule]
\titlespacing{\section}{0pt}{10pt}{10pt}
"""

    preamble += r"""
% 超链接设置
\usepackage[unicode, draft=false]{hyperref}
\definecolor{linkcolour}{rgb}{0,0.2,0.6}
\hypersetup{colorlinks,breaklinks,urlcolor=linkcolour,linkcolor=linkcolour}

% 防止溢出
\newcolumntype{C}{>{\centering\arraybackslash}X}
\newlength{\fullcollw}
\setlength{\fullcollw}{0.47\textwidth}

% 工作经历环境定义
\newenvironment{jobshort}[2]
    {
    \begin{tabularx}{\linewidth}{@{}l X r@{}}
    \textbf{#1} & \hfill &  #2 \\[3.75pt]
    \end{tabularx}
    }
    {
    }

\newenvironment{joblong}[2]
    {
    \begin{tabularx}{\linewidth}{@{}l X r@{}}
    \textbf{#1} & \hfill &  #2 \\[3.75pt]
    \end{tabularx}
    \begin{minipage}[t]{\linewidth}
    \begin{itemize}[nosep,after=\strut, leftmargin=1em, itemsep=3pt,label=--]
    }
    {
    \end{itemize}
    \end{minipage}    
    }

% 页面设置
\pagestyle{empty}
\setlength{\parskip}{6pt}
\setlength{\parindent}{0pt}
\raggedright
\sloppy
\emergencystretch=3em
\tolerance=1000
\hbadness=10000

\setlength{\lineskip}{0pt}
\setlength{\baselineskip}{1.1\baselineskip}

\binoppenalty=10000
\relpenalty=10000

\begin{document}
"""

    if chinese:
        content = r"{\cnfont" + "\n" + body + "\n}"
    else:
        content = body

    return preamble + content + r"""
\end{document}
"""


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
                p1 = subprocess.run(
                    cmd, cwd=tmpdir_path, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, timeout=timeout_sec
                )
                logger.info(f"Running pdflatex: {' '.join(cmd)} (2/2)")
                p2 = subprocess.run(
                    cmd, cwd=tmpdir_path, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, timeout=timeout_sec
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"LaTeX 编译超过 {timeout_sec}s 超时。")
            if p2.returncode != 0 or not pdf_path_tmp.exists():
                log = (p1.stdout or "") + "\n" + (p2.stdout or "")
                raise RuntimeError(f"pdflatex 编译失败：\n{log}")

        final_tex = upload_dir / f"{file_id}.tex"
        final_pdf = upload_dir / f"{file_id}.pdf"
        shutil.move(str(tex_path), str(final_tex))
        shutil.move(str(pdf_path_tmp), str(final_pdf))

    return str(final_tex), str(final_pdf), file_id


def gen_file_id(prefix: str = "resume") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# 主要 API：生成简历（支持：上传简历文件 或 手动简历 JSON + JD 文件）
@bp.post("/api/resume/generate")
def api_resume_generate():
    """
    输入：
      - 必须：jobDescription 文件 (field: jobDescription)
      - 二选一：
        a) 上传简历文件 (field: resume)
        b) 前端表单传 manualResume JSON (field: manualResume)

    流程：
      1. 保存原始文件到磁盘（若有简历文件）
      2. 读取并截断 resume_text / jd_text
      3. 检测语言、构造 prompt
      4. 调用 Qwen 生成 Markdown 简历
      5. Markdown -> LaTeX -> PDF，保存 .md / .pdf 到磁盘
      6. 返回 generatedResume / downloadMd / downloadPdf / resumeSaved / jdSaved / warnings
    """
    ensure_dirs()

    resume = request.files.get("resume")
    jd = request.files.get("jobDescription")

    # 可选：manualResume JSON
    manual_resume_raw = request.form.get("manualResume")
    manual_resume = None
    warnings = []

    if manual_resume_raw:
        try:
            manual_resume = json.loads(manual_resume_raw)
        except json.JSONDecodeError:
            logger.warning("manualResume 字段 JSON 解析失败，将忽略该字段")
            warnings.append("manualResume JSON parse error, ignored.")
            manual_resume = None

    manual_resume_text = manual_resume_to_text(manual_resume) if manual_resume else ""
    has_manual_resume_text = bool(manual_resume_text.strip())

    # JD 必须有
    if not jd:
        return jsonify({"success": False, "message": "Job description file is required."}), 400

    # 校验扩展名
    if resume and not ext_ok(resume.filename):
        return jsonify({"success": False, "message": "Unsupported resume file type"}), 400
    if not ext_ok(jd.filename):
        return jsonify({"success": False, "message": "Unsupported job description file type"}), 400

    # 必须提供：简历文件 或 manualResume
    if not resume and not has_manual_resume_text:
        return jsonify({"success": False, "message": "Provide either a resume file or manual resume data."}), 400

    # 1) 保存原始文件（只有 resume / jd；manualResume 只是 JSON，不落盘）
    if resume:
        resume_path = save_file(resume, Config.RESUME_DIR)
    else:
        resume_path = None
    jd_path = save_file(jd, Config.JD_DIR)

    # 2) 读取文本
    if resume_path:
        resume_text, w1 = read_text_from_file(resume_path)
    else:
        # 只用手动简历
        resume_text = manual_resume_text
        if not resume_text:
            return jsonify({"success": False, "message": "Manual resume data is empty."}), 400
        w1 = None

    jd_text, w2 = read_text_from_file(jd_path)
    warnings.extend([w for w in (w1, w2) if w])

    # 3) 截断
    resume_text, w3 = truncate_text(resume_text, Config.MAX_INPUT_CHARS)
    jd_text, w4 = truncate_text(jd_text, Config.MAX_INPUT_CHARS)
    warnings.extend([w for w in (w3, w4) if w])

    # 4) 检测语言
    resume_lang = detect_language(resume_text)
    jd_lang = detect_language(jd_text)
    target_lang = jd_lang if jd_lang == resume_lang else (jd_lang if jd_lang == 'zh' else resume_lang)
    logger.info(f"检测到简历语言: {resume_lang}, JD语言: {jd_lang}, 使用目标语言: {target_lang}")

    # 5) 组装 Prompt
    base_prompt = build_resume_prompt(resume_text, jd_text, language=target_lang)

    # 文件前缀
    file_id = gen_file_id()

    # 6) 系统提示词
    if target_lang == 'zh':
        system_prompt = (
            "你是一位资深的简历优化专家和AI招聘助手。\n"
            "请严格按照用户提供的详细要求生成简历。\n"
            "关键要求：\n"
            "1. 输出纯Markdown格式，不要包含代码块标记（不要用 ``` 包裹）\n"
            "2. 第一行必须是候选人真实姓名，格式为：# 姓名\n"
            "3. 第二行是联系方式，用 | 分隔\n"
            "4. 使用 ## 作为章节标题\n"
            "5. 所有客观信息必须严格遵照个人信息库，不能篡改或夸大\n"
            "6. 使用STAR法则和量化指标描述经历\n"
            "7. 所有内容必须使用中文"
        )
    else:
        system_prompt = (
            "You are a senior resume optimization expert and AI recruitment assistant.\n"
            "Please strictly follow the detailed requirements provided by the user to generate the resume.\n"
            "Key Requirements:\n"
            "1. Output pure Markdown format, do NOT include code block markers (do NOT wrap in ```)\n"
            "2. The first line must be the candidate's real name, formatted as: # Name\n"
            "3. The second line is contact information, separated by |\n"
            "4. Use ## for section headings\n"
            "5. All objective information must strictly follow the personal information database, no modification or exaggeration allowed\n"
            "6. Use STAR method and quantitative metrics to describe experiences\n"
            "7. All content must be in English"
        )

    try:
        # 7) 调用 Qwen 生成 Markdown
        logger.info(f"开始调用 Qwen API 生成简历，file_id: {file_id}")
        client = get_qwen_client()  # 延迟初始化，确保读取到最新的环境变量
        completion = client.chat.completions.create(
            model=os.getenv("QWEN_MODEL", "qwen-plus"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": base_prompt},
            ],
            temperature=0.3,
        )

        raw_md = completion.choices[0].message.content or ""
        generated_md = strip_code_fences(raw_md)

        if not generated_md:
            logger.warning("Qwen API 返回的内容为空")
            return jsonify({"success": False, "message": "生成的简历内容为空，请重试"}), 500

        logger.info(f"Qwen API 返回内容长度: {len(generated_md)} 字符")

        # 8) 保存 Markdown
        upload_dir = Path(getattr(Config, "UPLOAD_DIR", getattr(Config, "OUTPUT_DIR", "uploads")))
        upload_dir.mkdir(parents=True, exist_ok=True)
        md_path = upload_dir / f"{file_id}.md"
        md_path.write_text(generated_md, encoding="utf-8")
        download_md = url_for("uploads.download_file", file_name=f"{file_id}.md", _external=True)
        logger.info(f"Markdown 文件已保存: {md_path}")

        # 9) 尝试生成 PDF
        download_pdf = None
        try:
            logger.info("开始生成 PDF...")
            latex_body = markdown_to_latex(generated_md)
            latex_text = wrap_into_template(latex_body, chinese=(target_lang == 'zh'))

            tex_path, pdf_path, _ = compile_latex_to_pdf(latex_text, file_id)
            download_pdf = url_for("uploads.download_file", file_name=f"{file_id}.pdf", _external=True)
            logger.info(f"PDF 生成成功: {pdf_path}")
        except Exception as latex_err:
            logger.warning(f"PDF 生成失败（不影响主流程）: {latex_err}")
            warnings.append(f"PDF generation skipped: {latex_err}")

        # 10) 返回
        logger.info(f"简历生成完成，file_id: {file_id}, 返回成功响应")
        return jsonify({
            "success": True,
            "generatedResume": generated_md,
            "fileId": file_id,
            "downloadMd": download_md,
            "downloadPdf": download_pdf,  # 可能为 None
            "resumeSaved": resume_path,   # 可能为 None（手动模式）
            "jdSaved": jd_path,
            "warnings": warnings,
        }), 200

    except Exception as e:
        logger.exception("调用 Qwen API / LaTeX 编译失败")
        return jsonify({"success": False, "message": f"生成失败: {e}"}), 500