#!/bin/bash
# 设置 Qwen/DashScope API 环境变量

# 激活 conda 环境 py39（如果还没有激活）
# conda activate py39

# 设置 DASHSCOPE_API_KEY
# 请将下面的占位符替换为您的实际 API Key
export DASHSCOPE_API_KEY="YOUR_DASHSCOPE_API_KEY_HERE"

# 设置模型名称（默认：qwen3-max）
export QWEN_MODEL="qwen3-max"
export INTERVIEW_EVAL_MODEL="qwen3-max"

# 使用 dashscope 库（推荐，默认）
export USE_DASHSCOPE_LIB="true"

# 可选：如果需要使用 openai 兼容模式，取消下面的注释
# export USE_DASHSCOPE_LIB="false"
# export QWEN_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"

# 讯飞实时语音转写标准版配置
# 请将下面的占位符替换为您的实际配置信息
export XFYUN_APPID="YOUR_XFYUN_APPID_HERE"
export XFYUN_API_KEY="YOUR_XFYUN_API_KEY_HERE"

echo "环境变量已设置："
echo "DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:0:20}..."
echo ""
echo "如需永久设置，请将上述 export 命令添加到 ~/.bashrc 或 ~/.zshrc"

echo "XFYUN_APPID=${XFYUN_APPID}"
echo "XFYUN_API_KEY=${XFYUN_API_KEY:0:10}..."
