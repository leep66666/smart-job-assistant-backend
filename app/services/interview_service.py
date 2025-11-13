import base64
import hashlib
import hmac
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename
import websocket
from ..config import Config
from .files import ensure_dirs

logger = logging.getLogger(__name__)


DEFAULT_QUESTION_DURATION = int(os.environ.get("INTERVIEW_QUESTION_DURATION", "180"))


@dataclass
class InterviewQuestion:
    id: str
    text: str
    duration_seconds: int = DEFAULT_QUESTION_DURATION


@dataclass
class AnswerRecord:
    question_id: str
    question_text: str
    transcript: str
    audio_path: str
    evaluation: Dict[str, object]
    duration_seconds: float
    warnings: List[str] = field(default_factory=list)


@dataclass
class InterviewSession:
    session_id: str
    questions: List[InterviewQuestion]
    current_index: int = 0
    created_at: float = field(default_factory=time.time)
    question_started_at: Optional[float] = field(default_factory=time.time)
    answers: Dict[str, AnswerRecord] = field(default_factory=dict)
    info: Dict[str, object] = field(default_factory=dict)


_SESSIONS: Dict[str, InterviewSession] = {}
_LOCK = threading.RLock()


def _default_questions() -> List[InterviewQuestion]:
    preset = [
        "请介绍一下你在上一份工作中最具挑战性的项目，以及你在其中扮演的角色。",
        "面对紧迫的截止日期时，你是如何平衡质量与速度的？请举例说明。",
        "描述一次你与跨职能团队合作的经历，你们如何解决分歧？",
        "如果加入我们团队，你认为自己可以在哪些方面带来独特价值？",
        "请分享一次你主动学习新技能并成功应用到工作的案例。",
    ]
    return [
        InterviewQuestion(id=f"q{i+1}", text=question)
        for i, question in enumerate(preset)
    ]


def _save_audio_file(session_id: str, question_id: str, file_storage: FileStorage) -> str:
    ensure_dirs()
    filename = secure_filename(file_storage.filename or "")
    _, ext = os.path.splitext(filename)
    if not ext:
        ext = ".webm"
    target_name = f"{session_id}-{question_id}-{uuid.uuid4().hex}{ext}"
    target_path = os.path.join(Config.INTERVIEW_AUDIO_DIR, target_name)
    file_storage.save(target_path)
    return target_path


def _convert_to_pcm16(audio_path: str) -> Tuple[Optional[Path], List[str]]:
    """
    Convert arbitrary audio file to 16kHz mono PCM using ffmpeg.
    Returns path to temp file and any warnings.
    """
    warnings: List[str] = []
    ffmpeg_path = shutil.which("ffmpeg")  # type: ignore[name-defined]
    if not ffmpeg_path:
        warnings.append("未找到 ffmpeg，可用 brew/apt 安装后再启用讯飞实时转写。")
        return None, warnings

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pcm")
    os.close(tmp_fd)
    cmd = [
        ffmpeg_path,
        "-y",
        "-i",
        audio_path,
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
        tmp_path,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return Path(tmp_path), warnings
    except subprocess.CalledProcessError as exc:
        warnings.append(f"ffmpeg 转换失败：{exc.stderr.decode('utf-8', errors='ignore')}")
        return None, warnings


def _integrate_chunks_with_qwen(chunks: List[str], logger_instance: logging.Logger) -> Optional[str]:
    """
    使用Qwen整合讯飞转写的所有片段，生成完整的文字内容
    
    Args:
        chunks: 所有文本片段列表
        logger_instance: 日志记录器
    
    Returns:
        整合后的文本，如果失败则返回None
    """
    try:
        # 获取Qwen配置
        api_key = os.getenv("QWEN_API_KEY") or os.getenv("INTERVIEW_EVAL_API_KEY")
        base_url = os.getenv("QWEN_BASE_URL") or os.getenv("INTERVIEW_EVAL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        
        if not api_key:
            logger_instance.debug("未配置QWEN_API_KEY，跳过Qwen整合")
            return None
        
        # 如果没有片段，直接返回
        if not chunks or len(chunks) == 0:
            return None
        
        # 如果只有一个片段，不需要整合
        if len(chunks) == 1:
            return None
        
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            logger_instance.warning("缺少openai库，无法使用Qwen整合功能")
            return None
        
        # 创建Qwen客户端
        client = OpenAI(api_key=api_key, base_url=base_url)
        
        # 构建提示词
        chunks_text = "\n".join([f"片段{i+1}: {chunk}" for i, chunk in enumerate(chunks)])
        
        system_prompt = """你是一个专业的文本整合助手。你的任务是将语音识别系统返回的多个逐步增长的文本片段整合成一段完整、流畅的文字。

这些片段是实时语音识别系统逐步识别出的结果，特点：
- 后面的片段通常包含前面片段的内容，但会更完整
- 片段之间可能有重复，需要去重
- 片段可能不完整，需要合并成完整句子
- 需要保持原文的意思、语气和逻辑顺序

整合要求：
1. 识别并去除重复内容（包括部分重复）
2. 保留最完整、最准确的信息
3. 按照时间顺序整合所有片段
4. 整合成一段流畅、连贯的文字，保持原文的意思和语气
5. 不要添加原文中没有的内容
6. 保持标点符号的正确使用

只返回整合后的完整文字，不要添加任何解释、说明或标记。"""
        
        user_prompt = f"""以下是语音识别系统返回的多个文本片段（按识别顺序排列），请整合成一段完整、流畅的文字：

{chunks_text}

请仔细分析所有片段，去除重复内容，保留最完整的信息，整合成一段完整、流畅的文字。注意：
- 后面的片段通常包含前面片段的内容，选择最完整的版本
- 保持原文的逻辑顺序和意思
- 确保整合后的文字完整、连贯、流畅

整合后的完整文字："""
        
        logger_instance.info(f"调用Qwen API整合 {len(chunks)} 个片段...")
        
        # 调用Qwen API
        completion = client.chat.completions.create(
            model=os.getenv("QWEN_MODEL", "qwen-plus"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,  # 使用最低温度以获得最确定的结果
        )
        
        integrated_text = completion.choices[0].message.content.strip()
        logger_instance.info(f"Qwen整合完成，结果长度: {len(integrated_text)} 字符")
        return integrated_text
        
    except Exception as e:
        logger_instance.warning(f"Qwen整合失败: {e}，将使用原始方法")
        return None


def _transcribe_audio_rtasr(audio_path: str, return_all_chunks: bool = False) -> Tuple[str, List[str]]:
    """
    调用讯飞实时语音转写 RTASR 服务。需配置：
    - XFYUN_APPID
    - XFYUN_API_KEY （接口密钥）
    可选：XFYUN_API_SECRET（如控制台提供）
    
    Args:
        audio_path: 音频文件路径
        return_all_chunks: 如果为True，返回所有片段列表（第一个元素）和警告列表；如果为False，返回最终文本和警告列表
    
    Returns:
        如果return_all_chunks=False: (最终文本, 警告列表)
        如果return_all_chunks=True: (所有片段列表, 警告列表) - 注意：第一个元素是列表而不是字符串
    """
    warnings: List[str] = []
    appid = os.getenv("XFYUN_APPID") or getattr(Config, "XFYUN_APPID", None)
    api_key = os.getenv("XFYUN_API_KEY") or getattr(Config, "XFYUN_API_KEY", None)

    if not appid or not api_key:
        error_msg = "未配置讯飞 APPID 或 API_KEY，已跳过实时转写。"
        if not appid:
            error_msg += " APPID未设置"
        else:
            error_msg += f" APPID={appid}"
        if not api_key:
            error_msg += " API_KEY未设置"
        else:
            error_msg += f" API_KEY已设置（长度: {len(api_key)}）"
        logger.warning(error_msg)
        warnings.append(error_msg)
        return "", warnings
    
    logger.info(f"讯飞配置检查通过: APPID={appid}, API_KEY长度={len(api_key)}")

    pcm_path, convert_warnings = _convert_to_pcm16(audio_path)
    warnings.extend(convert_warnings)
    if pcm_path is None:
        return "", warnings

    # 设置讯飞转写专用日志文件
    xfyun_log_dir = os.path.join(Config.UPLOAD_ROOT, "logs", "xfyun")
    os.makedirs(xfyun_log_dir, exist_ok=True)
    xfyun_log_file = os.path.join(xfyun_log_dir, f"xfyun_rtasr_{int(time.time())}.log")
    
    # 创建文件日志处理器
    file_handler = logging.FileHandler(xfyun_log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(file_formatter)
    
    # 获取讯飞转写专用的logger
    xfyun_logger = logging.getLogger(f"{__name__}.xfyun_rtasr")
    xfyun_logger.addHandler(file_handler)
    xfyun_logger.setLevel(logging.DEBUG)
    xfyun_logger.info(f"讯飞实时转写日志文件: {xfyun_log_file}")

    result_chunks: List[str] = []
    final_result: Optional[str] = None  # 存储最后一个完整结果（ls:true）
    event = threading.Event()
    error_occurred = False

    def _on_message(ws, message):  # type: ignore[no-redef]
        nonlocal error_occurred, final_result
        try:
            payload = json.loads(message)
            logger.info(f"讯飞实时转写收到消息: {payload}")
            xfyun_logger.info(f"讯飞实时转写收到消息: {payload}")
        except json.JSONDecodeError as e:
            error_msg = f"讯飞实时转写返回无法解析: {e}"
            logger.error(error_msg)
            warnings.append(error_msg)
            return

        code = payload.get("code")
        action = payload.get("action")
        
        # code 可能是字符串 '0' 或整数 0，需要统一处理
        # code=0 或 code='0' 表示成功，code=None 也表示成功（某些消息可能没有code字段）
        # 只有当 code 存在且不等于 0 或 '0' 时才是错误
        code_int = None
        if code is not None:
            try:
                code_int = int(code) if isinstance(code, str) else code
            except (ValueError, TypeError):
                # 如果无法转换为整数，当作错误处理
                code_int = -1
        
        if code_int is not None and code_int != 0:
            error_msg = f"讯飞实时转写错误 code={code} msg={payload.get('message')}"
            logger.error(error_msg)
            warnings.append(error_msg)
            error_occurred = True
            event.set()
            return
        
        # code=0 或 code='0' 或 code=None 都是正常的，继续处理
        logger.info(f"讯飞实时转写消息 code={code}, action={action}")
        
        if action == "started":
            logger.info("讯飞实时转写连接已建立")
            return
        if action == "result":
            # 按照官方demo：result消息的data字段是JSON字符串，包含识别结果
            data_str = payload.get("data", "")
            if data_str:
                try:
                    # 解析data字段中的JSON字符串
                    data_obj = json.loads(data_str)
                    # 检查是否是最后一个完整结果（ls:true）
                    is_final = data_obj.get("ls", False)
                    
                    # 提取识别文本：data.cn.st.rt[0].ws[].cw[].w
                    text_parts = []
                    cn = data_obj.get("cn", {})
                    st = cn.get("st", {})
                    rt = st.get("rt", [])
                    for rt_item in rt:
                        ws = rt_item.get("ws", [])
                        for ws_item in ws:
                            cw = ws_item.get("cw", [])
                            for cw_item in cw:
                                word = cw_item.get("w", "")
                                if word:
                                    text_parts.append(word)
                    
                    if text_parts:
                        text = "".join(text_parts)
                        result_chunks.append(text)
                        logger.info(f"讯飞实时转写识别到文本: {text} (ls={is_final})")
                        xfyun_logger.info(f"讯飞实时转写识别到文本: {text} (ls={is_final})")
                        
                        # 如果是最后一个完整结果，保存它
                        # 但如果最终结果太短（只有标点符号），可能不是真正的最终结果
                        if is_final:
                            # 如果最终结果太短（少于3个字符），可能只是标点符号
                            # 这种情况下，我们会在后面使用最后一个非最终结果
                            if len(text.strip()) >= 3:
                                final_result = text
                                logger.info(f"讯飞实时转写收到最终结果: {text}")
                            else:
                                logger.warning(f"讯飞实时转写最终结果太短（可能只是标点）: {text}，将使用最后一个完整片段")
                    else:
                        logger.debug(f"讯飞实时转写 result 消息但无文本，data: {data_str[:200]}")
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning(f"解析识别结果失败: {e}, data: {data_str[:200]}")
                    # 如果解析失败，至少保存原始数据
                    result_chunks.append(data_str)
            else:
                logger.debug(f"讯飞实时转写 result 消息但data为空，payload: {payload}")
        elif action == "error":
            error_desc = payload.get("desc", "")
            error_code = payload.get("code", "")
            error_msg = f"讯飞实时转写返回错误: code={error_code}, desc={error_desc}, payload={payload}"
            logger.error(error_msg)
            warnings.append(f"讯飞实时转写错误: {error_desc}")
            error_occurred = True
            event.set()
        elif action == "finished":
            logger.info("讯飞实时转写已完成")
            # finished 消息表示服务器处理完成，立即设置事件
            # 不需要延迟，因为所有结果应该已经收到了
            event.set()
        elif action == "closed":
            logger.info("讯飞实时转写连接已关闭")
            # 连接关闭时设置事件，但可能已经收到了结果
            event.set()
        elif action is None:
            # 某些消息可能没有 action 字段，记录但不处理
            logger.debug(f"讯飞实时转写消息无 action 字段: {payload}")
        else:
            logger.info(f"讯飞实时转写未知 action: {action}, payload: {payload}")

    def _on_error(ws, error):  # type: ignore[no-redef]
        nonlocal error_occurred
        error_msg = f"讯飞实时转写连接异常: {error}"
        logger.error(error_msg)
        warnings.append(error_msg)
        error_occurred = True
        event.set()

    def _on_close(ws, *args):  # type: ignore[no-redef]
        logger.info("讯飞实时转写 WebSocket 连接已关闭")
        event.set()

    def _on_open(ws):  # type: ignore[no-redef]
        logger.info("讯飞实时转写 WebSocket 连接已打开，开始发送音频数据")
        xfyun_logger.info("讯飞实时转写 WebSocket 连接已打开，开始发送音频数据")
        def run():
            try:
                pcm_file_size = os.path.getsize(pcm_path)
                logger.info(f"开始发送音频文件，大小: {pcm_file_size} 字节")
                xfyun_logger.info(f"开始发送音频文件，大小: {pcm_file_size} 字节")
                
                # 计算音频时长（PCM 16kHz 16bit mono = 32000 字节/秒）
                audio_duration_seconds = pcm_file_size / 32000.0
                xfyun_logger.info(f"估算音频时长: {audio_duration_seconds:.2f} 秒")
                
                # 按照官方demo方式：直接发送二进制数据，不使用JSON格式
                with open(pcm_path, "rb") as pcm_stream:
                    frame_size = int(os.getenv("XFYUN_FRAME_SIZE", "1280"))
                    chunk_count = 0
                    send_interval = 0.04  # 40ms，与16kHz采样率匹配（1280字节=640采样点≈40ms）
                    
                    while True:
                        chunk = pcm_stream.read(frame_size)
                        if not chunk:
                            break
                        
                        # 关键修复：直接发送二进制数据（按照官方demo）
                        ws.send(chunk)
                        chunk_count += 1
                        time.sleep(send_interval)
                    
                    logger.info(f"音频数据发送完成，共发送 {chunk_count} 个数据块")
                    xfyun_logger.info(f"音频数据发送完成，共发送 {chunk_count} 个数据块")
                    
                    # 发送结束标志（按照官方demo格式）
                    end_tag = '{"end": true}'
                    ws.send(end_tag.encode('utf-8'))
                    logger.info("已发送结束标志 (end: true)")
                    xfyun_logger.info("已发送结束标志 (end: true)")
                    logger.info("等待服务器返回识别结果...")
                    xfyun_logger.info("等待服务器返回识别结果...")

            except Exception as exc:
                error_msg = f"发送音频失败：{exc}"
                logger.error(error_msg, exc_info=True)
                warnings.append(error_msg)
                error_occurred = True
                event.set()

        threading.Thread(target=run, daemon=True).start()

    try:
        import websocket  # type: ignore
    except ImportError:
        warnings.append("缺少 websocket-client 库，请运行 pip install websocket-client")
        try:
            os.remove(pcm_path)
        except OSError:
            pass
        return "", warnings

    ts = str(int(time.time()))
    md5_hash = hashlib.md5((appid + ts).encode("utf-8")).hexdigest()
    signa = hmac.new(api_key.encode("utf-8"), md5_hash.encode("utf-8"), hashlib.sha1).digest()
    signa_b64 = quote(base64.b64encode(signa))

    # 使用ws://而不是wss://（根据官方demo）
    url = f"ws://rtasr.xfyun.cn/v1/ws?appid={appid}&ts={ts}&signa={signa_b64}"
    logger.info(f"讯飞实时转写 WebSocket URL: ws://rtasr.xfyun.cn/v1/ws?appid={appid}&ts={ts}&signa=...")

    ws_app = websocket.WebSocketApp(
        url,
        on_message=_on_message,
        on_error=_on_error,
        on_close=_on_close,
        on_open=_on_open,
    )

    # 根据音频文件大小动态计算超时时间
    # PCM 16kHz 16bit mono = 32000 字节/秒
    # 超时时间 = 音频时长 + 发送时间 + 处理时间（至少30秒缓冲）
    pcm_file_size = os.path.getsize(pcm_path)
    audio_duration_seconds = pcm_file_size / 32000.0
    send_time_seconds = audio_duration_seconds * 1.1  # 发送时间约为音频时长的1.1倍
    buffer_seconds = 30.0  # 处理缓冲时间
    calculated_timeout = audio_duration_seconds + send_time_seconds + buffer_seconds
    
    # 使用环境变量配置的最小超时时间，或计算出的超时时间，取较大值
    min_timeout = float(os.getenv("XFYUN_TIMEOUT", "60"))
    timeout_seconds = max(min_timeout, calculated_timeout)
    
    logger.info(f"开始连接讯飞实时转写，音频时长: {audio_duration_seconds:.2f}秒，超时时间: {timeout_seconds:.2f}秒")
    xfyun_logger.info(f"开始连接讯飞实时转写，音频文件大小: {pcm_file_size} 字节，音频时长: {audio_duration_seconds:.2f}秒，超时时间: {timeout_seconds:.2f}秒")
    
    try:
        # 在单独的线程中运行 WebSocket
        ws_thread = threading.Thread(target=ws_app.run_forever, daemon=True)
        ws_thread.start()
        
        # 等待事件，直到收到 finished/closed 或超时
        # 注意：需要等待足够长的时间让服务器处理音频并返回结果
        event_triggered = event.wait(timeout=timeout_seconds)
        
        if not event_triggered:
            logger.warning(f"讯飞实时转写超时（{timeout_seconds:.2f}秒），可能音频文件过大或网络问题")
            xfyun_logger.warning(f"讯飞实时转写超时（{timeout_seconds:.2f}秒），可能音频文件过大或网络问题")
            warnings.append(f"讯飞实时转写超时（{timeout_seconds:.2f}秒），可能音频文件过大或网络问题")
            try:
                ws_app.close()
            except Exception:
                pass
        else:
            logger.info("讯飞实时转写事件已触发")
            xfyun_logger.info("讯飞实时转写事件已触发")
            # 即使事件已触发，也等待一小段时间确保收到所有消息
            time.sleep(0.5)
            
    except Exception as exc:
        error_msg = f"连接讯飞实时转写失败：{exc}"
        logger.error(error_msg, exc_info=True)
        warnings.append(error_msg)
    finally:
        try:
            os.remove(pcm_path)
            logger.debug(f"已删除临时 PCM 文件: {pcm_path}")
        except OSError as e:
            logger.warning(f"删除临时 PCM 文件失败: {e}")

    # 收集所有有效的片段（长度>=3，排除最终的那个标点）
    valid_chunks = []
    for chunk in result_chunks:
        chunk_stripped = chunk.strip()
        if len(chunk_stripped) >= 3:  # 跳过太短的片段（可能是标点或噪音）
            valid_chunks.append(chunk_stripped)
    
    # 如果有最终结果，也加入有效片段列表
    if final_result and len(final_result.strip()) >= 3:
        final_stripped = final_result.strip()
        if final_stripped not in valid_chunks:  # 避免重复
            valid_chunks.append(final_stripped)
    
    # 如果请求返回所有片段，直接返回
    if return_all_chunks:
        logger.info(f"返回所有片段: {len(valid_chunks)} 个有效片段")
        return valid_chunks, warnings
    
    # 尝试使用Qwen整合所有片段（如果配置了Qwen API）
    # 检查是否启用Qwen整合（默认启用，可通过环境变量禁用）
    use_qwen_integration = os.getenv("USE_QWEN_INTEGRATION", "true").lower() in ("true", "1", "yes")
    qwen_transcript = None
    
    if use_qwen_integration and valid_chunks and len(valid_chunks) > 1:
        qwen_transcript = _integrate_chunks_with_qwen(valid_chunks, logger)
    
    # 如果Qwen整合成功，使用整合结果；否则使用原始方法
    if qwen_transcript and len(qwen_transcript.strip()) > 0:
        transcript = qwen_transcript
        logger.info(f"讯飞实时转写结果: 使用Qwen整合结果，长度: {len(transcript)} 字符")
        xfyun_logger.info(f"讯飞实时转写结果: 使用Qwen整合结果，长度: {len(transcript)} 字符")
    elif valid_chunks:
        # 使用原始方法：选择最长片段
        if len(valid_chunks) == 1:
            # 如果只有一个有效片段，直接使用
            transcript = valid_chunks[0]
            logger.info(f"讯飞实时转写结果: 使用唯一有效片段，长度: {len(transcript)} 字符")
            xfyun_logger.info(f"讯飞实时转写结果: 使用唯一有效片段，长度: {len(transcript)} 字符")
        else:
            # 改进的去重策略：
            # 讯飞实时转写的特点：逐步识别，后面的片段通常包含前面片段的内容，但会更完整
            # 策略：从所有有效片段中选择最长的片段（包括最终结果）
            
            # 查找最长的完整片段（按中文字符和字母数字计算）
            best_chunk = valid_chunks[0]
            best_length = len("".join(c for c in best_chunk if c.isalnum() or '\u4e00' <= c <= '\u9fff'))
            
            # 遍历所有片段，找到最长的
            for chunk in valid_chunks:
                chunk_length = len("".join(c for c in chunk if c.isalnum() or '\u4e00' <= c <= '\u9fff'))
                if chunk_length > best_length:
                    best_chunk = chunk
                    best_length = chunk_length
            
            # 使用最长的片段
            transcript = best_chunk
            
            logger.info(f"讯飞实时转写结果: 从 {len(valid_chunks)} 个有效片段中选择最长片段，长度: {len(transcript)} 字符")
            xfyun_logger.info(f"讯飞实时转写结果: 从 {len(valid_chunks)} 个有效片段中选择最长片段，长度: {len(transcript)} 字符")
    else:
        transcript = ""
        logger.warning("讯飞实时转写未返回有效文本")
    
    logger.info(f"讯飞实时转写识别到 {len(result_chunks)} 个文本片段，最终文本长度: {len(transcript)} 字符")
    xfyun_logger.info(f"讯飞实时转写识别到 {len(result_chunks)} 个文本片段，最终文本长度: {len(transcript)} 字符")
    xfyun_logger.info(f"最终转录文本: {transcript}")
    
    # 移除文件日志处理器，避免日志文件持续增长
    xfyun_logger.removeHandler(file_handler)
    file_handler.close()
    
    if error_occurred:
        logger.warning("讯飞实时转写过程中发生错误")
        if not transcript:
            warnings.append("讯飞实时转写过程中发生错误，未获取到有效文本")
    elif not transcript:
        logger.warning("讯飞实时转写未返回有效文本")
        warnings.append("讯飞实时转写未返回有效文本，可能是音频质量问题或静音")
    else:
        logger.info(f"讯飞实时转写成功，识别文本: {transcript[:100]}...")
    
    return transcript, warnings


def _transcribe_audio(audio_path: str) -> Tuple[str, List[str]]:
    """
    调用配置的语音转写服务。当前实现仅支持讯飞实时语音转写 (RTASR)。
    """
    provider_raw = os.getenv("INTERVIEW_ASR_PROVIDER", "rtasr")
    provider = provider_raw.lower().strip()
    warnings: List[str] = []
    
    logger.info(f"ASR 提供商配置: INTERVIEW_ASR_PROVIDER='{provider_raw}' (处理后: '{provider}')")

    # 支持多种形式的rtasr配置：rtasr, rt, 空字符串
    if provider in ("", "rtasr", "rt") or provider.startswith("rtasr"):
        logger.info("使用讯飞实时语音转写 (RTASR)")
        transcript, more_warnings = _transcribe_audio_rtasr(audio_path)
        warnings.extend(more_warnings)
        return transcript, warnings

    logger.warning(f"不支持的 ASR 提供商：'{provider}'，请设置 INTERVIEW_ASR_PROVIDER=rtasr")
    warnings.append(f"不支持的 ASR 提供商：{provider}，请设置 INTERVIEW_ASR_PROVIDER=rtasr。")
    transcript = ""
    return transcript, warnings


_EVAL_CLIENT = None


def _get_eval_client():
    global _EVAL_CLIENT
    if _EVAL_CLIENT is not None:
        return _EVAL_CLIENT

    api_key = os.getenv("INTERVIEW_EVAL_API_KEY") or os.getenv("QWEN_API_KEY")
    base_url = os.getenv("INTERVIEW_EVAL_BASE_URL") or os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    if not api_key:
        logger.warning("未配置评估模型API密钥（INTERVIEW_EVAL_API_KEY 或 QWEN_API_KEY）")
        return None

    try:
        from openai import OpenAI  # type: ignore

        # 默认使用Qwen API的base_url
        if not base_url:
            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        
        logger.info(f"创建评估模型客户端: base_url={base_url}")
        _EVAL_CLIENT = OpenAI(api_key=api_key, base_url=base_url)
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.exception("创建评估模型客户端失败")
        raise RuntimeError(f"无法创建评估模型客户端：{exc}") from exc
    return _EVAL_CLIENT


def _evaluate_answer(question: str, transcript: str) -> Tuple[Dict[str, object], List[str]]:
    model_name = os.getenv("INTERVIEW_EVAL_MODEL", "qwen-plus")
    warnings: List[str] = []
    if not transcript.strip():
        warnings.append("未获取到有效转写文本，建议重新录制。")
        return {
            "overallScore": 0,
            "summary": "未识别到有效回答内容。",
            "strengths": [],
            "improvements": ["请确保麦克风正常工作并重新作答。"],
        }, warnings

    try:
        client = _get_eval_client()
    except RuntimeError as exc:
        warnings.append(str(exc))
        client = None

    if client:
        try:
            system_prompt = (
                "You are an experienced interview coach. "
                "Return strict JSON with keys overallScore (0-100), summary (string), "
                "strengths (array of strings), improvements (array of strings). "
                "Focus on relevance, structure, and communication."
            )
            user_prompt = json.dumps(
                {
                    "question": question,
                    "answerTranscript": transcript,
                },
                ensure_ascii=False,
            )
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            content = completion.choices[0].message.content or ""
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("评估模型返回格式异常")
            return parsed, warnings
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.exception("调用评估模型失败")
            warnings.append(f"评估模型调用失败：{exc}")

    # Fallback heuristic evaluation
    word_count = len(transcript.split())
    score = min(100, 40 + word_count * 1.5)
    if word_count < 20:
        feedback = "回答较为简短，建议补充细节和实例。"
    elif word_count < 60:
        feedback = "回答包含关键信息，可以进一步突出成果和量化指标。"
    else:
        feedback = "回答较为完整，注意结构清晰、重点突出。"

    return {
        "overallScore": round(score, 1),
        "summary": feedback,
        "strengths": [
            "自动评估：回答长度大于 {} 个词，说明表达较为完整。".format(word_count)
        ],
        "improvements": [
            "接入真实评估模型后可获得更细致的反馈。",
        ],
    }, warnings


def _build_markdown_report(session: InterviewSession) -> str:
    lines = [
        f"# 面试评估报告",
        f"- Session ID: {session.session_id}",
        f"- 题目数量: {len(session.questions)}",
        f"- 完成时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}",
        "",
    ]

    total_score = 0.0
    answered = 0

    for question in session.questions:
        answer = session.answers.get(question.id)
        lines.append(f"## 问题：{question.text}")
        if answer:
            answered += 1
            score = answer.evaluation.get("overallScore")
            if isinstance(score, (int, float)):
                total_score += float(score)
            lines.append(f"- 回答时长：{answer.duration_seconds:.1f} 秒")
            lines.append(f"- 语音转写：\n\n{answer.transcript or '（无内容）'}\n")
            lines.append(f"- 评分：{score if score is not None else 'N/A'}")
            summary = answer.evaluation.get("summary") or ""
            if summary:
                lines.append(f"- 评估摘要：{summary}")

            strengths = answer.evaluation.get("strengths") or []
            improvements = answer.evaluation.get("improvements") or []
            if strengths:
                lines.append("- 优势：")
                for item in strengths:
                    lines.append(f"  - {item}")
            if improvements:
                lines.append("- 改进建议：")
                for item in improvements:
                    lines.append(f"  - {item}")
        else:
            lines.append("- （该题未作答）")
        lines.append("")

    if answered > 0:
        avg_score = total_score / answered
        lines.insert(
            4,
            f"- 平均得分：{avg_score:.1f}",
        )
    else:
        lines.insert(
            4,
            "- 平均得分：N/A",
        )

    return "\n".join(lines).strip() + "\n"


def create_session(job_description_text: Optional[str] = None) -> InterviewSession:
    questions = _default_questions()
    session = InterviewSession(
        session_id=uuid.uuid4().hex,
        questions=questions,
        question_started_at=time.time(),
        info={"jobDescription": job_description_text},
    )
    with _LOCK:
        _SESSIONS[session.session_id] = session
    return session


def get_session(session_id: str) -> InterviewSession:
    with _LOCK:
        session = _SESSIONS.get(session_id)
        if not session:
            raise KeyError("会话不存在或已过期")
        return session


def submit_answer(
    session_id: str,
    question_id: str,
    audio_file: FileStorage,
    elapsed_seconds: Optional[float] = None,
) -> Tuple[AnswerRecord, Optional[str], Optional[str], List[str]]:
    with _LOCK:
        session = _SESSIONS.get(session_id)
        if not session:
            raise KeyError("会话不存在或已过期")

        if session.current_index >= len(session.questions):
            raise ValueError("所有面试题已作答完成")

        expected_question = session.questions[session.current_index]
        if expected_question.id != question_id:
            raise ValueError("题目顺序不正确，请按照给出的顺序回答。")

        start_ts = session.question_started_at or time.time()
        audio_path = _save_audio_file(session_id, question_id, audio_file)

    transcript, asr_warnings = _transcribe_audio(audio_path)
    evaluation, eval_warnings = _evaluate_answer(expected_question.text, transcript)
    warnings = asr_warnings + eval_warnings

    duration = elapsed_seconds if elapsed_seconds is not None else time.time() - start_ts
    record = AnswerRecord(
        question_id=expected_question.id,
        question_text=expected_question.text,
        transcript=transcript,
        audio_path=audio_path,
        evaluation=evaluation,
        duration_seconds=max(duration, 0.0),
        warnings=warnings,
    )

    with _LOCK:
        session = _SESSIONS[session_id]
        session.answers[expected_question.id] = record
        session.current_index += 1
        session.question_started_at = time.time() if session.current_index < len(session.questions) else None
        _SESSIONS[session_id] = session
        next_question = (
            session.questions[session.current_index]
            if session.current_index < len(session.questions)
            else None
        )

    next_question_id = next_question.id if next_question else None
    next_question_text = next_question.text if next_question else None
    return record, next_question_id, next_question_text, warnings


def build_report(session_id: str) -> Tuple[Dict[str, object], str]:
    session = get_session(session_id)
    report_items = []
    total_score = 0.0
    answered = 0

    for question in session.questions:
        answer = session.answers.get(question.id)
        item = {
            "questionId": question.id,
            "question": question.text,
            "durationSeconds": None,
            "transcript": None,
            "evaluation": None,
            "warnings": [],
        }
        if answer:
            item.update(
                {
                    "durationSeconds": answer.duration_seconds,
                    "transcript": answer.transcript,
                    "evaluation": answer.evaluation,
                    "warnings": answer.warnings,
                }
            )
            score = answer.evaluation.get("overallScore")
            if isinstance(score, (int, float)):
                total_score += float(score)
                answered += 1
        report_items.append(item)

    average_score = round(total_score / answered, 1) if answered else None
    summary = {
        "sessionId": session.session_id,
        "questionCount": len(session.questions),
        "answeredCount": answered,
        "averageScore": average_score,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
    }

    markdown = _build_markdown_report(session)
    ensure_dirs()
    filename = f"{session.session_id}-report.md"
    path = os.path.join(Config.INTERVIEW_REPORT_DIR, filename)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(markdown)

    return {
        "summary": summary,
        "items": report_items,
        "downloadName": filename,
    }, markdown


def reset_sessions():
    with _LOCK:
        _SESSIONS.clear()

