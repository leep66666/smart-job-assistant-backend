from typing import Optional, List
from . import db
from .models import FileRecord, GenerationRecord

def create_file_record(kind: str, filename: str, path: str, size: int) -> FileRecord:
    rec = FileRecord(kind=kind, filename=filename, path=path, size=size)
    db.session.add(rec)
    db.session.commit()
    return rec

def create_generation_record(file_id: str, kind: str, md_path: str, pdf_path: str, warnings: str = "") -> GenerationRecord:
    rec = GenerationRecord(file_id=file_id, kind=kind, md_path=md_path, pdf_path=pdf_path, warnings=warnings)
    db.session.add(rec)
    db.session.commit()
    return rec
