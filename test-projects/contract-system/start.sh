#!/bin/bash
# 合同管理系统 - 启动脚本

echo "==================================="
echo "   合同管理系统启动脚本"
echo "==================================="

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 初始化数据库并生成测试数据
echo ""
echo "1. 初始化数据库和测试数据..."
cd "$SCRIPT_DIR/backend"
python3 seed_data.py

# 启动后端
echo ""
echo "2. 启动后端服务 (端口 8001)..."
cd "$SCRIPT_DIR/backend"
nohup python3 main.py > /tmp/contract-system-backend.log 2>&1 &
BACKEND_PID=$!
sleep 2

# 检查后端是否启动成功
if curl -s http://localhost:8001/api/dashboard/stats > /dev/null 2>&1; then
    echo "   后端启动成功! PID: $BACKEND_PID"
else
    echo "   后端启动失败，请查看日志: /tmp/contract-system-backend.log"
    exit 1
fi

# 启动前端
echo ""
echo "3. 启动前端服务..."
cd "$SCRIPT_DIR/frontend"
nohup python3 -m http.server 3001 > /tmp/contract-system-frontend.log 2>&1 &
FRONTEND_PID=$!
sleep 1

echo "   前端启动成功! PID: $FRONTEND_PID"

echo ""
echo "==================================="
echo "   系统启动完成!"
echo "==================================="
echo ""
echo "前端访问: http://localhost:3001"
echo "后端 API: http://localhost:8001"
echo "API 文档: http://localhost:8001/docs"
echo ""
echo "停止服务:"
echo "  kill $BACKEND_PID  # 停止后端"
echo "  kill $FRONTEND_PID # 停止前端"
echo ""
echo "按 Ctrl+C 退出"
