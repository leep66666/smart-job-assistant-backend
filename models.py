from datetime import datetime
from . import db

class FileRecord(db.Model):
    __tablename__ = "files"
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(32), nullable=False)
    filename = db.Column(db.String(256), nullable=False)
    path = db.Column(db.String(512), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GenerationRecord(db.Model):
    __tablename__ = "generations"
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.String(64), nullable=False, index=True)
    kind = db.Column(db.String(32), nullable=False)
    md_path = db.Column(db.String(512), nullable=False)
    pdf_path = db.Column(db.String(512), nullable=False)
    warnings = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
