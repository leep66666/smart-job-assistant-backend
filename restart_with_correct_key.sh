#!/bin/bash
# 停止后端服务，设置正确的 API Key，然后重启

echo "=== 1. 停止现有后端服务 ==="
pkill -f "python.*run.py" || echo "  没有运行的后端服务"
sleep 2

echo ""
echo "=== 2. 设置正确的环境变量 ==="
# 请从 .env.local 文件或环境变量中读取配置
# 或者手动设置：
# export DASHSCOPE_API_KEY="YOUR_DASHSCOPE_API_KEY_HERE"
# export QWEN_MODEL="qwen3-max"
# export INTERVIEW_EVAL_MODEL="qwen3-max"
# export USE_DASHSCOPE_LIB="true"
# export XFYUN_APPID="YOUR_XFYUN_APPID_HERE"
# export XFYUN_API_KEY="YOUR_XFYUN_API_KEY_HERE"

# 尝试从 .env.local 加载
if [ -f .env.local ]; then
    echo "  从 .env.local 加载配置..."
    set -a
    source .env.local
    set +a
else
    echo "  警告: .env.local 文件不存在，请手动设置环境变量"
fi

echo "   ✓ DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:0:20}..."
echo "   ✓ QWEN_MODEL=${QWEN_MODEL}"
echo "   ✓ USE_DASHSCOPE_LIB=${USE_DASHSCOPE_LIB}"
echo "   ✓ XFYUN_APPID=${XFYUN_APPID}"
echo "   ✓ XFYUN_API_KEY=${XFYUN_API_KEY:0:10}..."

echo ""
echo "=== 3. 验证环境变量 ==="
python3 << 'PYTHON_EOF'
import os
api_key = os.getenv("DASHSCOPE_API_KEY")
xfyun_appid = os.getenv("XFYUN_APPID")
xfyun_api_key = os.getenv("XFYUN_API_KEY")

if api_key and len(api_key) > 30:
    print("   ✓ DASHSCOPE_API_KEY 正确设置")
else:
    print(f"   ✗ DASHSCOPE_API_KEY 不正确: {api_key[:30] if api_key else '未设置'}...")

if xfyun_appid and len(xfyun_appid) > 0:
    print(f"   ✓ XFYUN_APPID 已设置: {xfyun_appid[:10]}...")
else:
    print("   ✗ XFYUN_APPID 未设置")

if xfyun_api_key and len(xfyun_api_key) > 20:
    print(f"   ✓ XFYUN_API_KEY 已设置: {xfyun_api_key[:10]}...")
else:
    print("   ✗ XFYUN_API_KEY 未设置或格式不正确")
PYTHON_EOF

echo ""
echo "=== 4. 启动后端服务 ==="
echo "请在当前终端运行："
echo ""
echo "  conda activate py39"
echo "  cd /Users/liruolin/Desktop/HKU/NLP/group/smart-job-assistant-backend"
echo "  python run.py"
echo ""
echo "或者运行："
echo "  source restart_with_correct_key.sh && conda activate py39 && python run.py"
