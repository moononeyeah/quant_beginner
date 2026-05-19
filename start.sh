#!/bin/bash
# Quant Beginner Streamlit 启动脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 检查虚拟环境
if [ ! -f ".venv/bin/streamlit" ]; then
    echo "❌ 未找到 .venv/bin/streamlit"
    echo "请先运行: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# 查找可用端口
PORT=8501
while lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; do
    PORT=$((PORT + 1))
done

echo "🚀 启动 Quant Beginner..."
echo "📍 项目目录: $SCRIPT_DIR"
echo "🌐 访问地址: http://localhost:$PORT"
echo ""

.venv/bin/streamlit run app.py \
    --server.port $PORT \
    --server.headless true \
    --browser.gatherUsageStats false \
    --server.maxUploadSize 200
