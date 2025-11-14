# app/extensions.py
from flask_sqlalchemy import SQLAlchemy

# 全局共享的 db 实例
db = SQLAlchemy()