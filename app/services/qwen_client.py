"""
Qwen API 客户端封装
支持两种调用方式：
1. dashscope 库直接调用（推荐，更稳定）
2. openai 库兼容模式（备选）
"""
import os
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# 优先使用哪种方式：'dashscope' 或 'openai'
USE_DASHSCOPE_LIB = os.getenv("USE_DASHSCOPE_LIB", "true").lower() in ("true", "1", "yes")


def _call_with_dashscope(
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    **kwargs
) -> Dict[str, Any]:
    """
    使用 dashscope 库直接调用 Qwen API
    """
    try:
        from dashscope import Generation
        import dashscope
        
        # 设置 base_url（使用 /api/v1 而不是 /compatible-mode/v1）
        dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'
        
        response = Generation.call(
            api_key=api_key,
            model=model,
            messages=messages,
            result_format="message",
            temperature=temperature,
            **kwargs
        )
        
        if response.status_code == 200:
            return {
                "success": True,
                "content": response.output.choices[0].message.content,
            }
        else:
            error_msg = f"HTTP返回码：{response.status_code}，错误码：{response.code}，错误信息：{response.message}"
            logger.error(f"dashscope API调用失败: {error_msg}")
            raise RuntimeError(error_msg)
            
    except ImportError:
        raise RuntimeError("dashscope 库未安装，请运行: pip install dashscope")
    except Exception as e:
        logger.error(f"dashscope 库调用异常: {e}")
        raise


def _call_with_openai(
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature: float = 0.7,
    **kwargs
) -> Dict[str, Any]:
    """
    使用 openai 库兼容模式调用 Qwen API
    """
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs
        )
        
        return {
            "success": True,
            "content": completion.choices[0].message.content or "",
        }
        
    except ImportError:
        raise RuntimeError("openai 库未安装，请运行: pip install openai")
    except Exception as e:
        logger.error(f"openai 兼容模式调用异常: {e}")
        raise


def call_qwen_api(
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    use_dashscope: Optional[bool] = None,
    **kwargs
) -> str:
    """
    调用 Qwen API，自动选择最佳方式
    
    Args:
        api_key: DashScope API Key
        model: 模型名称（如 'qwen-plus', 'qwen3-max'）
        messages: 消息列表
        temperature: 温度参数
        use_dashscope: 是否使用 dashscope 库（None 时根据环境变量决定）
        **kwargs: 其他参数
    
    Returns:
        返回生成的内容字符串
    
    Raises:
        RuntimeError: API调用失败时抛出异常
    """
    if use_dashscope is None:
        use_dashscope = USE_DASHSCOPE_LIB
    
    # 优先使用 dashscope 库
    if use_dashscope:
        try:
            result = _call_with_dashscope(
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                **kwargs
            )
            return result["content"]
        except Exception as e:
            logger.warning(f"dashscope 库调用失败，尝试使用 openai 兼容模式: {e}")
            # 如果失败，回退到 openai 兼容模式
            try:
                result = _call_with_openai(
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    **kwargs
                )
                return result["content"]
            except Exception as fallback_error:
                logger.error(f"openai 兼容模式也失败: {fallback_error}")
                raise RuntimeError(f"API调用失败：dashscope方式失败({e})，openai兼容模式也失败({fallback_error})")
    else:
        # 直接使用 openai 兼容模式
        try:
            result = _call_with_openai(
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                **kwargs
            )
            return result["content"]
        except Exception as e:
            logger.warning(f"openai 兼容模式调用失败，尝试使用 dashscope 库: {e}")
            # 如果失败，回退到 dashscope 库
            try:
                result = _call_with_dashscope(
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    **kwargs
                )
                return result["content"]
            except Exception as fallback_error:
                logger.error(f"dashscope 库也失败: {fallback_error}")
                raise RuntimeError(f"API调用失败：openai兼容模式失败({e})，dashscope方式也失败({fallback_error})")


def get_api_key() -> Optional[str]:
    """
    获取 API Key，按优先级查找
    """
    return (
        os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("INTERVIEW_EVAL_API_KEY")
        or os.getenv("QWEN_API_KEY")
    )

