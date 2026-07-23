#!/bin/bash
# ============================================================
# 股票投资模型 · Oracle Cloud 一键部署脚本
# ============================================================
# 在 Oracle Cloud ARM 实例上运行此脚本
# 用法：bash deploy_oracle.sh
# ============================================================

set -e

echo "========================================"
echo "股票投资模型 · Oracle Cloud 部署"
echo "========================================"

# 1. 系统更新 + 基础工具
echo "▶ [1/7] 系统更新..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip git nginx > /dev/null 2>&1

# 2. 创建项目目录
echo "▶ [2/7] 创建项目目录..."
APP_DIR="$HOME/stock_model"
mkdir -p "$APP_DIR"
cd "$APP_DIR"

# 3. 如果已有代码（从本地上传或 git clone），跳过
if [ ! -f "dashboard/standalone_app.py" ]; then
    echo "⚠️ 未检测到项目代码。"
    echo "请用以下方式之一上传代码到 $APP_DIR："
    echo "  方式A: scp -r ./stock_model/* ubuntu@<服务器IP>:~/stock_model/"
    echo "  方式B: git clone <你的仓库> $APP_DIR"
    echo "  方式C: 用 FileZilla 等 SFTP 工具上传"
    echo ""
    echo "上传完成后，重新运行此脚本：bash deploy_oracle.sh"
    exit 1
fi

# 4. Python 虚拟环境 + 依赖
echo "▶ [3/7] 安装 Python 依赖..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install flask pandas numpy matplotlib requests akshare -q
# PaddleOCR 可选（ARM 上安装较慢，先跳过，OCR 功能后期补）
echo "  （PaddleOCR 在 ARM 上安装较慢，暂跳过。截图 OCR 功能后期补装）"

# 5. Systemd 服务（开机自启 + 崩溃重启）
echo "▶ [4/7] 配置系统服务..."
SERVICE_FILE="/tmp/stock_model.service"
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Stock Model Flask App
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python dashboard/standalone_app.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
sudo cp "$SERVICE_FILE" /etc/systemd/system/stock_model.service
sudo systemctl daemon-reload
sudo systemctl enable stock_model
sudo systemctl restart stock_model
echo "  ✅ 服务已启动（开机自启 + 崩溃自动重启）"

# 6. Nginx 反向代理（80 端口，免输端口号）
echo "▶ [5/7] 配置 Nginx 反向代理..."
NGINX_CONF="/tmp/stock_model_nginx"
cat > "$NGINX_CONF" << 'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 20M;  # 允许上传截图

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
    }
}
EOF
sudo cp "$NGINX_CONF" /etc/nginx/sites-available/stock_model
sudo ln -sf /etc/nginx/sites-available/stock_model /etc/nginx/sites-enabled/stock_model
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t 2>/dev/null
sudo systemctl restart nginx
echo "  ✅ Nginx 已配置（80 端口）"

# 7. 防火墙
echo "▶ [6/7] 开放防火墙端口..."
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
sudo iptables -I INPUT -p tcp --dport 5001 -j ACCEPT 2>/dev/null || true
sudo netfilter-persistent save 2>/dev/null || true
echo "  ✅ 端口 80/5001 已开放"

# 8. 验证
echo "▶ [7/7] 验证..."
sleep 3
if curl -s http://127.0.0.1:5001/ | grep -q "投资模型"; then
    echo "  ✅ Flask 服务正常运行"
else
    echo "  ⚠️ Flask 未响应，检查日志：journalctl -u stock_model -f"
fi
if curl -s http://127.0.0.1:80/ | grep -q "投资模型"; then
    echo "  ✅ Nginx 反向代理正常"
else
    echo "  ⚠️ Nginx 未响应，检查：sudo nginx -t"
fi

# 获取公网 IP
PUB_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null || echo "未知")
echo ""
echo "========================================"
echo "🎉 部署完成！"
echo "========================================"
echo ""
echo "📱 手机访问地址："
echo "   http://$PUB_IP"
echo ""
echo "   （4G/WiFi 都能用，直接浏览器打开）"
echo ""
echo "🔧 管理命令："
echo "   查看状态: sudo systemctl status stock_model"
echo "   查看日志: sudo journalctl -u stock_model -f"
echo "   重启服务: sudo systemctl restart stock_model"
echo "   停止服务: sudo systemctl stop stock_model"
echo ""
echo "⚠️ Oracle Cloud 安全组："
echo "   还需在 Oracle 控制台 → 实例 → 安全列表 → 添加 0.0.0.0/0 TCP 80 入站规则"
echo "   （否则公网仍访问不了）"
echo ""
echo "📖 详细教程见：docs/Oracle部署教程.md"
