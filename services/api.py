import ollama

def ping_ollama():
    # 若失败会抛异常，供 /health 使用
    return ollama.list()

def list_ollama_models():
    m = ollama.list().get("models", [])
    return [x.get("model") for x in m]