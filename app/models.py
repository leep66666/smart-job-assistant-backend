# app/models.py
from datetime import datetime
from app.extensions import db


class Resume(db.Model):
    __tablename__ = "resumes"

    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.String(64), index=True)  # 你已有的 file_id 可以挂上来
    full_name = db.Column(db.String(128), nullable=False)
    phone_code = db.Column(db.String(8))
    phone_number = db.Column(db.String(32))
    email = db.Column(db.String(128))

    programming_skills = db.Column(db.Text)
    office_skills = db.Column(db.Text)
    language_skills = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    educations = db.relationship("Education", backref="resume", cascade="all, delete-orphan")
    internships = db.relationship("Internship", backref="resume", cascade="all, delete-orphan")
    work_experiences = db.relationship("WorkExperience", backref="resume", cascade="all, delete-orphan")
    projects = db.relationship("Project", backref="resume", cascade="all, delete-orphan")
    competitions = db.relationship("Competition", backref="resume", cascade="all, delete-orphan")


class Education(db.Model):
    __tablename__ = "educations"

    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.id"), nullable=False)

    degree = db.Column(db.String(128))
    school = db.Column(db.String(256))
    start_date = db.Column(db.String(32))
    end_date = db.Column(db.String(32))
    major = db.Column(db.String(128))
    gpa = db.Column(db.String(32))


class Internship(db.Model):
    __tablename__ = "internships"

    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.id"), nullable=False)

    company = db.Column(db.String(256))
    title = db.Column(db.String(128))
    timeframe = db.Column(db.String(64))
    responsibilities = db.Column(db.Text)


class WorkExperience(db.Model):
    __tablename__ = "work_experiences"

    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.id"), nullable=False)

    company = db.Column(db.String(256))
    title = db.Column(db.String(128))
    timeframe = db.Column(db.String(64))
    responsibilities = db.Column(db.Text)
    departure_reason = db.Column(db.String(256))


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.id"), nullable=False)

    name = db.Column(db.String(256))
    timeframe = db.Column(db.String(64))
    description = db.Column(db.Text)


class Competition(db.Model):
    __tablename__ = "competitions"

    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.id"), nullable=False)

    name = db.Column(db.String(256))
    level = db.Column(db.String(64))
    result = db.Column(db.String(128))

class ResumeUser(db.Model):
    __tablename__ = "resume_users"

    # 对应：id BIGINT PRIMARY KEY AUTO_INCREMENT
    id = db.Column(db.BigInteger, primary_key=True)

    # ===== Personal Information =====
    full_name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    country_code = db.Column(db.String(16), nullable=True)
    phone_number = db.Column(db.String(64), nullable=True)
    github = db.Column(db.String(255), nullable=True)
    linkedin = db.Column(db.String(255), nullable=True)

    # ===== Education (Up to 3) =====
    edu1_degree = db.Column(db.String(255), nullable=True)
    edu1_school = db.Column(db.String(255), nullable=True)
    edu1_start = db.Column(db.String(32), nullable=True)
    edu1_end = db.Column(db.String(32), nullable=True)
    edu1_major = db.Column(db.String(255), nullable=True)
    edu1_gpa = db.Column(db.String(64), nullable=True)

    edu2_degree = db.Column(db.String(255), nullable=True)
    edu2_school = db.Column(db.String(255), nullable=True)
    edu2_start = db.Column(db.String(32), nullable=True)
    edu2_end = db.Column(db.String(32), nullable=True)
    edu2_major = db.Column(db.String(255), nullable=True)
    edu2_gpa = db.Column(db.String(64), nullable=True)

    edu3_degree = db.Column(db.String(255), nullable=True)
    edu3_school = db.Column(db.String(255), nullable=True)
    edu3_start = db.Column(db.String(32), nullable=True)
    edu3_end = db.Column(db.String(32), nullable=True)
    edu3_major = db.Column(db.String(255), nullable=True)
    edu3_gpa = db.Column(db.String(64), nullable=True)

    # ===== Internships (Up to 3) =====
    int1_company = db.Column(db.String(255), nullable=True)
    int1_title = db.Column(db.String(255), nullable=True)
    int1_period = db.Column(db.String(64), nullable=True)
    int1_responsibility = db.Column(db.Text, nullable=True)

    int2_company = db.Column(db.String(255), nullable=True)
    int2_title = db.Column(db.String(255), nullable=True)
    int2_period = db.Column(db.String(64), nullable=True)
    int2_responsibility = db.Column(db.Text, nullable=True)

    int3_company = db.Column(db.String(255), nullable=True)
    int3_title = db.Column(db.String(255), nullable=True)
    int3_period = db.Column(db.String(64), nullable=True)
    int3_responsibility = db.Column(db.Text, nullable=True)

    # ===== Work Experience (Up to 3) =====
    work1_company = db.Column(db.String(255), nullable=True)
    work1_title = db.Column(db.String(255), nullable=True)
    work1_period = db.Column(db.String(64), nullable=True)
    work1_responsibility = db.Column(db.Text, nullable=True)
    work1_reason_leave = db.Column(db.String(255), nullable=True)

    work2_company = db.Column(db.String(255), nullable=True)
    work2_title = db.Column(db.String(255), nullable=True)
    work2_period = db.Column(db.String(64), nullable=True)
    work2_responsibility = db.Column(db.Text, nullable=True)
    work2_reason_leave = db.Column(db.String(255), nullable=True)

    work3_company = db.Column(db.String(255), nullable=True)
    work3_title = db.Column(db.String(255), nullable=True)
    work3_period = db.Column(db.String(64), nullable=True)
    work3_responsibility = db.Column(db.Text, nullable=True)
    work3_reason_leave = db.Column(db.String(255), nullable=True)

    # ===== Projects (Up to 3) =====
    proj1_name = db.Column(db.String(255), nullable=True)
    proj1_period = db.Column(db.String(64), nullable=True)
    proj1_details = db.Column(db.Text, nullable=True)

    proj2_name = db.Column(db.String(255), nullable=True)
    proj2_period = db.Column(db.String(64), nullable=True)
    proj2_details = db.Column(db.Text, nullable=True)

    proj3_name = db.Column(db.String(255), nullable=True)
    proj3_period = db.Column(db.String(64), nullable=True)
    proj3_details = db.Column(db.Text, nullable=True)

    # ===== Skills =====
    programming_skills = db.Column(db.Text, nullable=True)
    office_skills = db.Column(db.Text, nullable=True)
    languages = db.Column(db.Text, nullable=True)

    # ===== Competitions (Up to 3) =====
    comp1_name = db.Column(db.String(255), nullable=True)
    comp1_award = db.Column(db.String(255), nullable=True)
    comp1_year = db.Column(db.String(16), nullable=True)

    comp2_name = db.Column(db.String(255), nullable=True)
    comp2_award = db.Column(db.String(255), nullable=True)
    comp2_year = db.Column(db.String(16), nullable=True)

    comp3_name = db.Column(db.String(255), nullable=True)
    comp3_award = db.Column(db.String(255), nullable=True)
    comp3_year = db.Column(db.String(16), nullable=True)

    # ===== Others =====
    others = db.Column(db.Text, nullable=True)

    # ===== Raw resume text =====
    resume_raw = db.Column(db.Text, nullable=True)

    # ===== Timestamps =====
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # 关联到多次生成记录
    generations = db.relationship("ResumeGeneration", backref="user", lazy=True)


class ResumeGeneration(db.Model):
    __tablename__ = "resume_generations"

    # 对应：id BIGINT / INT UNSIGNED AUTO_INCREMENT
    id = db.Column(db.BigInteger, primary_key=True)

    # 外键：指向 resume_users.id（你的表里是 BIGINT，我们也用 BigInteger）
    user_id = db.Column(db.BigInteger, db.ForeignKey("resume_users.id"), nullable=False)

    # 本次上传/生成的唯一 ID（例如 resume-abcd12）
    file_id = db.Column(db.String(64), unique=True, nullable=False)

    # 用户上传的原始简历文本
    resume_text = db.Column(db.Text, nullable=False)

    # 用户上传的职位描述
    jd_text = db.Column(db.Text, nullable=False)

    # 模型生成的 Markdown 简历
    generated_md = db.Column(db.Text, nullable=False)

    # 语言 (zh/en 等)
    target_lang = db.Column(db.String(8), nullable=True)

    # 保存文件名（不是路径），用于现有 uploads 接口下载
    md_filename = db.Column(db.String(255), nullable=True)
    pdf_filename = db.Column(db.String(255), nullable=True)

    # 原始上传的文件的服务器路径（可选）
    resume_file_path = db.Column(db.String(512), nullable=True)
    jd_file_path = db.Column(db.String(512), nullable=True)

    # 可选字段
    prompt_used = db.Column(db.Text, nullable=True)
    snapshot_profile = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )