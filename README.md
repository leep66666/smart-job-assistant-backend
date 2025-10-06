使用Python（3.10版本以上）完成开发
数据库：MySQL 8.x
混用Flask和Fastapi，用反向代理汇总
后端结构：
smart-job-assistant/
├─ app/
│  ├─ __init__.py          # 应用工厂：注册蓝图、CORS、DB、CLI
│  ├─ config.py            # 配置（含 DATABASE_URL、本地LLM版本等）
│  ├─ extensions.py        # 第三方扩展实例：db = SQLAlchemy()
│  ├─ models.py            # ORM 模型：FileRecord / GenerationRecord
│  ├─ db.py                # DAO：对外暴露数据库接口函数（create/list/…）
│  ├─ routes/
│  │  ├─ uploads.py        # /api/upload（入库）
│  │  ├─ resume.py         # /api/resume/generate（入库）
│  │  └─ interview.py      # /api/interview/questions
│  └─ services/
│     ├─ files.py          # 保存/抽取/截断/写PDF
│     ├─ prompts.py        # Prompt 构建
│     ├─ llm.py            # 预留 Ollama 封装（可能要使用本地大模型完成问答环节）
│     └─ api.py            # 预留大模型 API
├─ run.py                  # 开发启动

