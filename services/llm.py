import ollama
import logging
from app.config import Config

logger = logging.getLogger(__name__)

def run_ollama(prompt: str, stream: bool = False) -> str:
    logger.info(f"Running ollama model={Config.OLLAMA_MODEL}, prompt_len={len(prompt)}")
    if not stream:
        resp = ollama.generate(
            model=Config.OLLAMA_MODEL,
            prompt=prompt,
            options={"temperature": Config.GEN_TEMPERATURE}
        )
        return resp.get("response", "")
    else:
        out = []
        for chunk in ollama.generate(
            model=Config.OLLAMA_MODEL,
            prompt=prompt,
            options={"temperature": Config.GEN_TEMPERATURE},
            stream=True
        ):
            out.append(chunk.get("response", ""))
        return "".join(out)