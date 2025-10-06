import os
import uuid
from datetime import datetime
from typing import Tuple, Optional, List
from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm

from app.config import Config

def ensure_dirs():
    os.makedirs(Config.RESUME_DIR, exist_ok=True)
    os.makedirs(Config.JD_DIR, exist_ok=True)
    os.makedirs(Config.OUTPUT_DIR, exist_ok=True)

def ext_ok(filename: str) -> bool:
    _, ext = os.path.splitext((filename or "").lower())
    return ext in Config.ALLOWED_EXTS

def save_file(file_storage, target_dir: str) -> str:
    original = secure_filename(file_storage.filename or "")
    _, ext = os.path.splitext(original)
    if not ext:
        ext = ".txt"
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(target_dir, name)
    file_storage.save(path)
    return os.path.abspath(path)

def read_text_from_file(path: str) -> Tuple[str, Optional[str]]:
    _, ext = os.path.splitext(path.lower())
    warn = None
    try:
        if ext == ".txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(), None
        elif ext == ".pdf":
            try:
                import PyPDF2
                text = []
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        text.append(page.extract_text() or "")
                return "\n".join(text), None
            except Exception as e:
                warn = f"PDF解析失败：{e}"
                return "", warn
        elif ext == ".docx":
            try:
                from docx import Document
            except Exception:
                warn = ("未安装或错误安装了 python-docx。"
                        "请执行：pip uninstall -y docx && pip install -U python-docx")
                return "", warn
            try:
                doc = Document(path)
                text = "\n".join(p.text for p in doc.paragraphs)
                return text, None
            except Exception as e:
                warn = f"DOCX解析失败：{e}"
                return "", warn
        else:
            return "", f"不支持的扩展名: {ext}"
    except Exception as e:
        return "", f"读取失败：{e}"

def truncate_text(s: str, max_chars: int) -> Tuple[str, Optional[str]]:
    if len(s) <= max_chars:
        return s, None
    return s[:max_chars] + f"\n\n...[Truncated to {max_chars} chars]", f"输入文本过长，已截断至 {max_chars} 字符。"

def write_pdf_from_markdown(md_text: str, pdf_path: str, title: str = "Customized Resume"):
    styles = getSampleStyleSheet()
    story: List = []
    cover_title = Paragraph(f"<b>{title}</b>", styles["Title"])
    from datetime import datetime as _dt
    cover_date = Paragraph(_dt.now().strftime("%Y-%m-%d %H:%M"), styles["Normal"])
    story.extend([Spacer(1, 30*mm), cover_title, Spacer(1, 5*mm), cover_date, Spacer(1, 20*mm)])
    body = Preformatted(md_text, styles["Code"])
    story.extend([body])

    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=14*mm, bottomMargin=16*mm)
    doc.build(story)

def write_outputs(md_content: str):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    import uuid as _uuid
    file_id = f"{ts}-{_uuid.uuid4().hex}"

    md_path = os.path.join(Config.OUTPUT_DIR, file_id + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    pdf_path = os.path.join(Config.OUTPUT_DIR, file_id + ".pdf")
    write_pdf_from_markdown(md_content, pdf_path, title="Job-Tailored Resume")
    return md_path, pdf_path, file_id