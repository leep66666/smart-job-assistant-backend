import ollama
import logging
import os
from app.config import Config

logger = logging.getLogger(__name__)

# 禁用代理，确保ollama直接连接本地服务
# 在模块加载时就禁用代理，并设置NO_PROXY
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(proxy_var, None)

# 设置NO_PROXY，确保localhost不使用代理
os.environ['NO_PROXY'] = 'localhost,127.0.0.1,::1,0.0.0.0'
os.environ['no_proxy'] = 'localhost,127.0.0.1,::1,0.0.0.0'

def run_ollama(prompt: str, stream: bool = False, timeout: int = 600) -> str:
    """
    运行ollama模型生成文本
    
    Args:
        prompt: 输入提示词
        stream: 是否使用流式输出（推荐使用True以避免超时）
        timeout: 超时时间（秒），默认600秒（10分钟）
    
    Returns:
        生成的文本
    """
    logger.info(f"Running ollama model={Config.OLLAMA_MODEL}, prompt_len={len(prompt)}, stream={stream}, timeout={timeout}s")
    
    try:
        # 创建ollama客户端，设置超时和host
        # 再次确保代理被禁用（在函数内部）
        for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
            os.environ.pop(proxy_var, None)
        
        # 创建ollama客户端，明确指定host和timeout，并禁用代理
        try:
            # 尝试创建带超时的客户端
            import inspect
            sig = inspect.signature(ollama.Client.__init__)
            params = {'host': 'http://localhost:11434'}
            if 'timeout' in sig.parameters:
                params['timeout'] = timeout
            # 尝试禁用代理 - 通过设置NO_PROXY环境变量
            # 将localhost添加到NO_PROXY，确保本地连接不使用代理
            no_proxy = os.environ.get('NO_PROXY', '') or os.environ.get('no_proxy', '')
            if 'localhost' not in no_proxy and '127.0.0.1' not in no_proxy:
                no_proxy_list = [x.strip() for x in no_proxy.split(',') if x.strip()]
                no_proxy_list.extend(['localhost', '127.0.0.1', '::1'])
                os.environ['NO_PROXY'] = ','.join(no_proxy_list)
                os.environ['no_proxy'] = ','.join(no_proxy_list)
                logger.info(f"设置NO_PROXY: {os.environ['NO_PROXY']}")
            
            client = ollama.Client(**params)
            logger.info(f"使用ollama客户端，host={params.get('host')}, timeout={params.get('timeout', 'default')}")
        except (TypeError, AttributeError, Exception) as e:
            # 如果Client不支持timeout参数，使用默认客户端
            logger.warning(f"ollama.Client初始化失败: {e}，使用默认客户端")
            try:
                client = ollama.Client(host='http://localhost:11434')
            except:
                # 最后尝试使用默认客户端
                client = ollama
                logger.warning("使用ollama默认客户端")
        
        if not stream:
            try:
                resp = client.generate(
                    model=Config.OLLAMA_MODEL,
                    prompt=prompt,
                    options={"temperature": Config.GEN_TEMPERATURE}
                )
                return resp.get("response", "")
            except Exception as e:
                logger.error(f"Ollama generate error: {e}")
                # 如果非流式失败，尝试使用流式
                logger.info("Retrying with stream mode...")
                return run_ollama(prompt, stream=True, timeout=timeout)
        else:
            out = []
            try:
                # 使用流式处理
                for chunk in client.generate(
                    model=Config.OLLAMA_MODEL,
                    prompt=prompt,
                    options={"temperature": Config.GEN_TEMPERATURE},
                    stream=True
                ):
                    chunk_response = chunk.get("response", "")
                    if chunk_response:
                        out.append(chunk_response)
                result = "".join(out)
                if not result:
                    raise ValueError("模型返回空响应")
                return result
            except Exception as stream_error:
                logger.error(f"流式处理失败: {stream_error}")
                # 如果流式失败，尝试非流式
                logger.info("尝试非流式处理...")
                try:
                    resp = client.generate(
                        model=Config.OLLAMA_MODEL,
                        prompt=prompt,
                        options={"temperature": Config.GEN_TEMPERATURE}
                    )
                    result = resp.get("response", "")
                    if not result:
                        raise ValueError("模型返回空响应")
                    return result
                except Exception as non_stream_error:
                    logger.error(f"非流式处理也失败: {non_stream_error}")
                    raise
    except Exception as e:
        logger.error(f"Ollama调用失败: {type(e).__name__}: {e}")
        raise