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
from app.extensions import db
from app.models import ResumeUser, ResumeGeneration

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
# 从环境变量读取 API key（必须设置，不允许硬编码）
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

if not QWEN_API_KEY:
    logger.error("QWEN_API_KEY 未设置，简历生成功能将无法正常工作。请设置环境变量 QWEN_API_KEY")
else:
    logger.info(f"QWEN_API_KEY 已配置（长度: {len(QWEN_API_KEY)}）")

client = OpenAI(
    api_key=QWEN_API_KEY,
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
        # 使用占位符方法：先用唯一占位符替换格式标记，转义文本，然后替换回格式标记
        # 使用不包含LaTeX特殊字符的占位符格式，避免被转义
        placeholders = {}
        placeholder_counter = [0]
        
        def get_placeholder():
            placeholder_counter[0] += 1
            # 使用不包含下划线和其他LaTeX特殊字符的占位符
            # 使用大写的PLACEHOLDER前缀和数字，避免与LaTeX特殊字符冲突
            return f"PLACEHOLDER{placeholder_counter[0]}PLACEHOLDER"
        
        # 先处理代码（避免与其他格式冲突）
        def repl_inline_code(m):
            placeholder = get_placeholder()
            inner = m.group(1)
            inner = inner.replace('\\', r'\textbackslash{}').replace('{', r'\{').replace('}', r'\}')
            placeholders[placeholder] = r'\texttt{' + inner + '}'
            return placeholder
        text = re.sub(r'`([^`]+)`', repl_inline_code, text)
        
        # 处理链接 [text](url)
        def repl_link(m):
            placeholder = get_placeholder()
            link_text = m.group(1)
            link_url = m.group(2)
            # URL 中的特殊字符需要转义
            link_url_escaped = link_url.replace('\\', r'\textbackslash{}').replace('{', r'\{').replace('}', r'\}').replace('#', r'\#').replace('$', r'\$').replace('%', r'\%').replace('&', r'\&').replace('_', r'\_').replace('^', r'\^{}').replace('~', r'\~{}')
            placeholders[placeholder] = r'\href{' + link_url_escaped + '}{' + escape_latex(link_text) + '}'
            return placeholder
        text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', repl_link, text)
        
        # 处理粗体 **text** 或 __text__
        def repl_bold(m):
            placeholder = get_placeholder()
            placeholders[placeholder] = r'\textbf{' + escape_latex(m.group(1)) + '}'
            return placeholder
        text = re.sub(r'\*\*([^\*]+)\*\*', repl_bold, text)
        text = re.sub(r'__([^_]+)__', repl_bold, text)
        
        # 处理斜体 *text* 或 _text_（不在粗体或代码中）
        def repl_italic(m):
            placeholder = get_placeholder()
            placeholders[placeholder] = r'\textit{' + escape_latex(m.group(1)) + '}'
            return placeholder
        text = re.sub(r'(?<!\*)\*([^\*]+)\*(?!\*)', repl_italic, text)
        text = re.sub(r'(?<!_)_([^_]+)_(?!_)', repl_italic, text)
        
        # 修复符号前后的空白：在符号前后添加LaTeX的不可断空格
        # 使用 ~ 来防止换行，但只在非列表项的情况下处理
        # 注意：这里假设列表项已经在之前被处理了，所以这里的文本是普通段落
        # 只处理被空格包围的符号，避免影响列表项
        text = re.sub(r'([^\s~\-])\s+\+\s+([^\s~\-])', r'\1~+~\2', text)  # + 前后使用 ~ 防止换行
        text = re.sub(r'([^\s~\-])\s+-\s+([^\s~\-])', r'\1~-~\2', text)  # - 前后（但不在行首，且不是列表项）
        text = re.sub(r'([^\s~])\s+=\s+([^\s~])', r'\1~=~\2', text)  # = 前后
        text = re.sub(r'([^\s~])\s+<\s+([^\s~])', r'\1~<~\2', text)  # < 前后
        text = re.sub(r'([^\s~])\s+>\s+([^\s~])', r'\1~>~\2', text)  # > 前后
        
        # 转义整个文本（占位符不包含LaTeX特殊字符，不会被转义）
        text = escape_latex(text)
        
        # 替换回格式标记
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
            out.append(line)  # verbatim 内不转义
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
            # 第一行是姓名，使用大标题居中格式
            if is_first_line:
                out.append(r'\begin{tabularx}{\linewidth}{@{} C @{}}')
                out.append(r'\Huge{' + title_text + r'} \\[7.5pt]')
                is_first_line = False
                i += 1
                # 检查下一行是否是联系方式
                if i < len(lines) and lines[i].strip() and not lines[i].startswith('#'):
                    contact_line = lines[i].strip()
                    # 处理联系方式（可能包含 | 分隔符）
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
                # 其他一级标题作为section
                out.append(r'\section{' + title_text + '}')
                i += 1
                continue

        # 列表项
        list_match = re.match(r'^\s*([-*•])\s+', line)
        if list_match:
            if not in_itemize:
                # 使用 enumitem 改进列表格式，防止溢出
                # 检查前一行是否是工作经历（以\end{tabularx}结尾）
                if out and out[-1].strip().endswith(r'\end{tabularx}'):
                    # 在工作经历后，使用minipage包装列表
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

        # 检查是否是工作经历或项目经历格式：**职位名称** (时间)
        job_match = re.match(r'^\s*\*\*([^\*]+)\*\*\s*\(([^\)]+)\)', line)
        if job_match:
            flush_itemize()
            job_title = job_match.group(1).strip()
            job_time = job_match.group(2).strip()
            # 使用tabularx格式：职位名称左对齐，时间右对齐
            out.append(r'\begin{tabularx}{\linewidth}{@{}l X r@{}}')
            out.append(r'\textbf{' + escape_latex(job_title) + r'} & \hfill & ' + escape_latex(job_time) + r' \\[3.75pt]')
            out.append(r'\end{tabularx}')
            i += 1
            continue

        # 普通段落 - 处理格式并防止溢出
        processed_line = process_inline_formatting(line)
        # 对于长段落，使用合适的换行设置
        # 不添加额外的minipage，让LaTeX自然处理换行
        out.append(processed_line)
        i += 1

    flush_itemize(check_next=False)
    # 确保关闭所有打开的minipage
    if in_minipage:
        out.append(r'\end{minipage}')
    return '\n'.join(out)

def wrap_into_template(body: str, chinese: bool = True) -> str:
    """
    使用改进的 LaTeX 模板，参考专业简历格式，防止内容溢出
    """
    # 基础包和设置
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
    
    # 中文字体支持
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
    
    # 继续添加必要的包
    preamble += r"""
% 自定义章节格式
"""
    # 根据语言设置章节格式
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
    
    # 继续添加必要的包
    preamble += r"""
% 超链接设置
\usepackage[unicode, draft=false]{hyperref}
\definecolor{linkcolour}{rgb}{0,0.2,0.6}
\hypersetup{colorlinks,breaklinks,urlcolor=linkcolour,linkcolor=linkcolour}

% 防止溢出
\newcolumntype{C}{>{\centering\arraybackslash}X}
\newlength{\fullcollw}
\setlength{\fullcollw}{0.47\textwidth}

% 工作经历环境定义（参考样例模板）
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
\setlength{\parindent}{0pt}  % 无段落缩进
\raggedright
\sloppy  % 允许更宽松的换行，防止溢出
\emergencystretch=3em  % 额外的紧急拉伸，防止溢出
\tolerance=1000  % 增加容忍度，允许更宽松的换行
\hbadness=10000  % 减少关于不良换行的警告

% 改进段落换行，减少不必要的空白
\setlength{\lineskip}{0pt}
\setlength{\baselineskip}{1.1\baselineskip}

% 防止单词在符号前后断开
\binoppenalty=10000  % 防止二元运算符前后换行
\relpenalty=10000    % 防止关系运算符前后换行

\begin{document}
"""
    
    # 内容包装
    # 对于中文，由于已经设置了默认字体，不需要额外的字体包装
    # 但如果需要确保所有内容都使用中文字体，可以保留cnfont包装
    if chinese:
        # 使用cnfont确保所有内容（包括标题）都使用中文字体
        content = r"{\cnfont" + "\n" + body + "\n}"
    else:
        content = body
    
    return preamble + content + r"""
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

# 主要 API：生成简历（Qwen Markdown -> LaTeX -> PDF，原始文件只走临时目录）
# 主要 API：生成简历（Qwen Markdown -> LaTeX -> PDF，DB-first + 不持久化原始文件）
# 主要 API：生成简历（Qwen Markdown -> LaTeX -> PDF，DB-first + 不持久化原始文件）
@bp.post("/api/resume/generate")
def api_resume_generate():
    """
    输入：上传的 resume / jobDescription 文件 + 可选的 manualResume JSON
    流程：
      1. 上传文件只写临时目录，用于解析文本，请求结束即删除，不落长期磁盘
      2. 解析并截断 resume_text / jd_text
      3. 检测语言、构造 prompt
      4. 写入数据库：resume_users / resume_generations
         - snapshot_profile 用来保存前端手动填写的 ManualResumeFormData JSON
      5. 调用 Qwen 生成 Markdown 简历
      6. Markdown -> LaTeX -> PDF，长期只保存 md/pdf
      7. 用生成结果回填 generation 记录
      8. 返回结构与老版本保持一致（尤其是 generatedResume / downloadPdf / resumeSaved / jdSaved / warnings）
    """
    ensure_dirs()

    # 0) 拿文件
    resume = request.files.get("resume")
    jd = request.files.get("jobDescription")
    if not resume or not jd:
        return jsonify({"success": False, "message": "Both files are required."}), 400
    if not ext_ok(resume.filename) or not ext_ok(jd.filename):
        return jsonify({"success": False, "message": "Unsupported file type"}), 400

    # 用前端传的 userIdentifier 当 email
    user_email = request.form.get("userIdentifier")

    # 可选：前端传来的手动简历 JSON，字段名 manualResume
    # 前端对应：formData.append('manualResume', JSON.stringify(manualResume));
    manual_resume_raw = request.form.get("manualResume")
    manual_resume = None

    # 兼容老的 warning 结构
    warnings = []

    if manual_resume_raw:
        try:
            manual_resume = json.loads(manual_resume_raw)
        except json.JSONDecodeError:
            logger.warning("manualResume 字段 JSON 解析失败，将忽略该字段")
            warnings.append("manualResume JSON parse error, ignored.")

    # 为了兼容你之前的返回结构，这里先定义占位变量
    # 我们现在不再长期保存原始上传文件，所以这俩会一直是 None
    resume_path = None
    jd_path = None

    try:
        # === 1) 原始文件只写临时目录，用完即删 ===
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            resume_tmp = tmpdir_path / (resume.filename or "resume")
            jd_tmp = tmpdir_path / (jd.filename or "jobDescription")

            resume.save(str(resume_tmp))
            jd.save(str(jd_tmp))

            resume_text, w1 = read_text_from_file(str(resume_tmp))
            jd_text, w2 = read_text_from_file(str(jd_tmp))
            warnings.extend([w for w in (w1, w2) if w])

        # === 2) 截断 ===
        resume_text, w3 = truncate_text(resume_text, Config.MAX_INPUT_CHARS)
        jd_text, w4 = truncate_text(jd_text, Config.MAX_INPUT_CHARS)
        warnings.extend([w for w in (w3, w4) if w])

        # === 3) 语言检测 ===
        resume_lang = detect_language(resume_text)
        jd_lang = detect_language(jd_text)
        target_lang = jd_lang if jd_lang == resume_lang else (jd_lang if jd_lang == "zh" else resume_lang)
        logger.info(f"检测到简历语言: {resume_lang}, JD语言: {jd_lang}, 使用目标语言: {target_lang}")

        # === 4) 组装 Prompt ===
        base_prompt = build_resume_prompt(resume_text, jd_text, language=target_lang)

        # 统一 fileId
        file_id = gen_file_id()

        # === 5) 系统提示词 ===
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

        # === 6) 写入数据库：ResumeUser + 初始 ResumeGeneration（还没生成简历） ===
        user = None
        if user_email:
            user = ResumeUser.query.filter_by(email=user_email).first()

        # 如果没找到用户，尽量用手动简历里的姓名 / 邮箱
        manual_personal = (manual_resume or {}).get("personal", {}) if manual_resume else {}

        if not user:
            user = ResumeUser(
                full_name=(manual_personal.get("fullName") or "Unknown"),
                email=(user_email or manual_personal.get("email")),
                resume_raw=resume_text,
            )
            db.session.add(user)
            db.session.flush()  # 拿到 user.id

        # snapshot_profile 用来保存前端传来的 ManualResumeFormData（如果有）
        snapshot_profile_json = json.dumps(manual_resume, ensure_ascii=False) if manual_resume else None

        generation = ResumeGeneration(
            user_id=user.id,
            file_id=file_id,
            resume_text=resume_text,
            jd_text=jd_text,
            generated_md="",
            target_lang=target_lang,
            md_filename=None,
            pdf_filename=None,
            resume_file_path=None,
            jd_file_path=None,
            prompt_used=base_prompt,
            snapshot_profile=snapshot_profile_json,
        )
        db.session.add(generation)
        db.session.flush()  # 拿到 generation.id

        # === 7) 调 Qwen 生成 Markdown（生成部分严格照你原来的逻辑） ===
        logger.info(f"开始调用 Qwen API 生成简历，file_id: {file_id}, generation_id: {generation.id}")
        completion = client.chat.completions.create(
            model="qwen-plus",
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
            db.session.rollback()
            return jsonify({"success": False, "message": "生成的简历内容为空，请重试"}), 500

        logger.info(f"Qwen API 返回内容长度: {len(generated_md)} 字符")

        # === 8) 存 Markdown -> 生成 downloadMd ===
        upload_dir = Path(getattr(Config, "UPLOAD_DIR", getattr(Config, "OUTPUT_DIR", "uploads")))
        upload_dir.mkdir(parents=True, exist_ok=True)
        md_path = upload_dir / f"{file_id}.md"
        md_path.write_text(generated_md, encoding="utf-8")
        download_md = url_for("uploads.download_file", file_name=f"{file_id}.md", _external=True)
        logger.info(f"Markdown 文件已保存: {md_path}")

        # === 9) 尝试生成 PDF ===
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

        # === 10) 回填 DB ===
        generation.generated_md = generated_md
        generation.md_filename = f"{file_id}.md"
        generation.pdf_filename = f"{file_id}.pdf" if download_pdf else None
        db.session.commit()

        # === 11) 返回：务必包含 generatedResume，前端才能切换到结果页 ===
        logger.info(f"简历生成完成，file_id: {file_id}, 返回成功响应")
        return jsonify({
            "success": True,
            "generatedResume": generated_md,
            "fileId": file_id,
            "downloadMd": download_md,
            "downloadPdf": download_pdf,   # 可能为 None
            "resumeSaved": resume_path,    # 现在就是 None，占位用
            "jdSaved": jd_path,            # 同上
            "warnings": warnings,
        }), 200

    except Exception as e:
        logger.exception("调用 Qwen API / LaTeX 编译或数据库写入失败")
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"success": False, "message": f"生成失败: {e}"}), 500