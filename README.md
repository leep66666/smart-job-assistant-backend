## 项目概述

`smart-job-assistant-backend` 基于 Flask 提供两大核心能力：

- **简历定制**：接收 JD/简历文件，调用 Qwen 模型生成定制化简历，同时输出 Markdown/PDF。
- **面试模拟**：接收候选人的语音回答，依托讯飞实时转写（RTASR）完成语音识别，再使用 Qwen 对回答做整合与评估。

前端项目位于 `../smart-job-assistant-frontend`，采用 Vite + React 实现。

---

## 运行前的环境准备

### 1. Python 依赖（后端）

后端推荐 Python 3.10+。请在项目根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` 中列出了后端使用的第三方库：

- `Flask` / `Flask-Cors`：HTTP API 与跨域支持
- `openai`：兼容 Qwen DashScope 接口的官方客户端
- `ollama`：本地快速校验模型可用性
- `python-docx`、`PyPDF2`、`reportlab`：处理简历/职位说明等文档
- `websocket-client`：与讯飞实时转写服务建立 WebSocket 连接

此外需要系统安装 `ffmpeg`（用于音频转码）。

### 2. Node 依赖（前端）

前端推荐 Node.js 18+。在 `../smart-job-assistant-frontend` 目录执行：

```bash
npm install
npm run dev        # 开发模式
npm run build      # 生产构建
```

---

## 关键环境变量

在启动前，请配置以下变量（可写入 `.env`）：

| 变量名 | 说明 |
| --- | --- |
| `QWEN_API_KEY` | Qwen 模型 API Key（DashScope 兼容模式） |
| `QWEN_BASE_URL` | Qwen API Base URL，默认为 `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `XFYUN_APPID` / `XFYUN_API_KEY` | 讯飞实时转写凭证 |
| `OLLAMA_MODEL` | 本地 Ollama 模型名称，可选 |
| `UPLOAD_ROOT` | 上传目录根路径，不设置则使用 `./uploads` |

---

## 运行方式

```bash
export FLASK_ENV=development  # 可选
python run.py
```

API 默认监听 `http://0.0.0.0:5000`。

---

## 面试模拟功能说明

1. **语音上传与实时转写**  
   前端会分段上传候选人的语音回答，后端采用讯飞 RTASR 建立 WebSocket 连接，实时接收文本片段并写入日志。

2. **文本去重与整合**  
   转写结束后，后端会将全部片段交由 Qwen 模型进行句子级去重、语义补全，生成最终回答文本。若 Qwen 不可用则回退为最长片段策略。

3. **答案评估**  
   对于每个问题，系统会将问题文本与最终回答交给评估模型，输出维度化反馈（结构、逻辑、提升建议等），并连同转写结果一起返回前端。

4. **日志与报告**  
   所有语音、中间日志与最终报告默认存储在 `uploads/interview/*` 目录，便于排查与复盘。

---

## 目录结构速览

```
smart-job-assistant-backend/
├── app/
│   ├── routes/          # Flask 蓝图（resume / interview / uploads）
│   ├── services/        # 文件处理、LLM、语音转写等核心逻辑
│   ├── config.py        # 全局配置
│   └── __init__.py      # 应用工厂
├── uploads/             # 运行期产生的文件
└── run.py               # Flask 启动入口
```

---

## 常见问题

- **Qwen 调用失败**：检查网络、API Key 是否正确，必要时可将 `USE_QWEN_INTEGRATION` 设为 `false` 跳过整合。
- **讯飞连接异常**：确认 AppID/API Key、白名单及网络通路；同时留意日志中 `xfyun_rtasr_*.log` 文件。
- **PDF 生成失败**：确保系统已安装 `libfreetype`、`libjpeg` 等 ReportLab 依赖，并正确安装 `reportlab`。
