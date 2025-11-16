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

---

## Qwen/DashScope API 配置说明

项目现已支持使用 DashScope API（百炼）调用 Qwen 模型。配置方式如下：

### 方式一：使用环境变量脚本（推荐）

```bash
# 激活 conda 环境
conda activate py39

# 运行设置脚本
source setup_env.sh

# 或者手动设置（请替换为您的实际 API Key）
export DASHSCOPE_API_KEY="YOUR_DASHSCOPE_API_KEY_HERE"
```

### 方式二：在 shell 配置文件中永久设置

将以下内容添加到 `~/.bashrc` 或 `~/.zshrc`：

```bash
export DASHSCOPE_API_KEY="YOUR_DASHSCOPE_API_KEY_HERE"
export XFYUN_APPID="YOUR_XFYUN_APPID_HERE"
export XFYUN_API_KEY="YOUR_XFYUN_API_KEY_HERE"
```

### 环境变量优先级

系统会按以下优先级查找 API Key：
1. `DASHSCOPE_API_KEY`（优先，百炼API Key）
2. `INTERVIEW_EVAL_API_KEY`
3. `QWEN_API_KEY`

### 默认配置

- **模型名称**: `qwen3-max`（可通过 `INTERVIEW_EVAL_MODEL` 环境变量修改）
- **Base URL**: `https://dashscope.aliyuncs.com/compatible-mode/v1`（可通过 `QWEN_BASE_URL` 或 `INTERVIEW_EVAL_BASE_URL` 环境变量修改）

### 验证配置

启动后端后，查看日志确认模型客户端是否成功创建：

```
INFO: 创建评估模型客户端: base_url=https://dashscope.aliyuncs.com/compatible-mode/v1
INFO: 开始生成面试问题，使用模型: qwen3-max
```

---

---

## Qwen API 调用方式说明

项目支持两种方式调用 Qwen API：

### 方式一：使用 dashscope 库（推荐，默认）

这是阿里云官方的 `dashscope` 库，直接调用 API，更稳定可靠。

**配置方式：**
```bash
export DASHSCOPE_API_KEY="YOUR_DASHSCOPE_API_KEY_HERE"
export USE_DASHSCOPE_LIB="true"  # 默认值，可选
```

### 方式二：使用 openai 兼容模式

使用 `openai` 库的兼容模式调用 DashScope API。

**配置方式：**
```bash
export DASHSCOPE_API_KEY="YOUR_DASHSCOPE_API_KEY_HERE"
export USE_DASHSCOPE_LIB="false"  # 强制使用 openai 兼容模式
```

### 自动回退机制

系统会优先使用配置的方式，如果失败会自动尝试另一种方式：
- 默认优先使用 `dashscope` 库
- 如果失败，自动回退到 `openai` 兼容模式
- 反之亦然

### 新的 API 封装函数

如果需要在代码中直接调用，可以使用 `app/services/qwen_client.py` 中的封装函数：

```python
from app.services.qwen_client import call_qwen_api, get_api_key

api_key = get_api_key()
messages = [
    {"role": "user", "content": "你好"}
]

# 调用 API（自动选择最佳方式）
response = call_qwen_api(
    api_key=api_key,
    model="qwen-plus",
    messages=messages,
    temperature=0.7,
)
```

---

