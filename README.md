使用Python（3.10版本以上）完成开发
数据库：MySQL 8.x
混用Flask和Fastapi，用反向代理汇总
后端结构：
smart-job-assistant/
├─ app/
│  ├─ __init__.py           # 应用工厂：注册蓝图、CORS、DB、CLI
│  ├─ config.py             # 配置（含 DATABASE_URL、本地LLM版本等）
│  ├─ extensions.py         # 第三方扩展实例：db = SQLAlchemy()
│  ├─ models.py             # ORM 模型：FileRecord / GenerationRecord
│  ├─ db.py                 # DAO：对外暴露数据库接口函数（create/list/…）
│  ├─ routes/
│  │  ├─ uploads.py         # /api/upload（文件上传入库）
│  │  ├─ resume.py          # /api/resume/generate（简历生成）
│  │  └─ interview.py       # /api/interview/questions（面试问题生成）
│  └─ services/
│     ├─ files.py           # 文件处理逻辑（保存/抽取/截断/写PDF）
│     ├─ prompts.py         # Prompt 构建工具
│     ├─ llm.py             # 本地 LLM（Ollama）封装
│     └─ api.py             # 远程大模型 API 调用
├─ run.py                   # 项目启动文件
└─ readme
