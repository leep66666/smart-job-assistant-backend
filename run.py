import os
from pathlib import Path
from app import create_app

def load_env_file(env_file: str = ".env.local"):
    """从 .env.local 文件加载环境变量"""
    env_path = Path(__file__).parent / env_file
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    # 只在环境变量未设置时设置
                    if key and not os.getenv(key):
                        os.environ[key] = value

if __name__ == "__main__":
    # 加载 .env.local 文件（如果存在）
    load_env_file()
    
    # 打印当前使用的 API Key（用于调试）
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY") or os.getenv("INTERVIEW_EVAL_API_KEY")
    if api_key:
        print(f"[INFO] 使用的 API Key: {api_key[:20]}...{api_key[-10:]}")
    else:
        print("[WARNING] 未找到 API Key 环境变量")
    
    port = int(os.environ.get("PORT", "5001"))
    app = create_app()
    app.run(host="0.0.0.0", port=port, debug=True)