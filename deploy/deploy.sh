#!/bin/bash
# ============================================================
# Multi-Agent 代码审计系统 - 一键部署脚本
# 适用系统: Ubuntu 22.04 / Debian 12
# 用法: sudo bash deploy.sh
# ============================================================

set -e

# 配置变量 (按需修改)
APP_NAME="multi-agent-audit"
APP_DIR="/opt/${APP_NAME}"
VENV_DIR="${APP_DIR}/venv"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOMAIN_OR_IP="${1:-$(hostname -I | awk '{print $1}')}"

echo "============================================"
echo "  Multi-Agent 代码审计系统 - 部署脚本"
echo "============================================"
echo "应用目录: ${APP_DIR}"
echo "域名/IP:  ${DOMAIN_OR_IP}"
echo ""

# 1. 安装系统依赖
echo "[1/7] 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv nginx > /dev/null

# 2. 创建应用目录并复制文件
echo "[2/7] 复制项目文件..."
mkdir -p "${APP_DIR}"
rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='db.sqlite3' --exclude='venv' --exclude='staticfiles' \
    "${REPO_DIR}/" "${APP_DIR}/"

# 3. 创建虚拟环境并安装依赖
echo "[3/7] 创建虚拟环境并安装依赖..."
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
pip install -q --upgrade pip
pip install -q -r "${APP_DIR}/requirements.txt"
pip install -q gunicorn

# 4. 数据库迁移 + 静态文件收集
echo "[4/7] 初始化数据库并收集静态文件..."
cd "${APP_DIR}"
export DJANGO_DEBUG=False
export DJANGO_SECRET_KEY=$(python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
export DJANGO_ALLOWED_HOSTS="${DOMAIN_OR_IP},localhost,127.0.0.1"

python manage.py migrate --run-syncdb
python manage.py collectstatic --noinput

# 种子数据 (可选)
echo "是否导入历史案例种子数据? (y/n)"
read -r seed_choice
if [ "$seed_choice" = "y" ] || [ "$seed_choice" = "Y" ]; then
    python manage.py seed_cases || true
fi

# 5. 生成 systemd 服务文件
echo "[5/7] 配置 systemd 服务..."
cat > /etc/systemd/system/${APP_NAME}.service << EOF
[Unit]
Description=Multi-Agent Code Audit System
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=${APP_DIR}
Environment="DJANGO_DEBUG=False"
Environment="DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}"
Environment="DJANGO_ALLOWED_HOSTS=${DOMAIN_OR_IP},localhost"
Environment="LLM_API_KEY=${LLM_API_KEY:-}"
ExecStart=${VENV_DIR}/bin/gunicorn config.wsgi:application -c gunicorn.conf.py
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 6. 配置 Nginx
echo "[6/7] 配置 Nginx..."
cat > /etc/nginx/sites-available/${APP_NAME} << EOF
server {
    listen 80;
    server_name ${DOMAIN_OR_IP};

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    location /static/ {
        alias ${APP_DIR}/staticfiles/;
        expires 30d;
    }

    location /media/ {
        alias ${APP_DIR}/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 300;
        proxy_read_timeout 300;
        proxy_send_timeout 300;
    }

    client_max_body_size 10M;
}
EOF

ln -sf /etc/nginx/sites-available/${APP_NAME} /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 设置权限
chown -R www-data:www-data "${APP_DIR}"
chmod -R 755 "${APP_DIR}"

# 7. 启动服务
echo "[7/7] 启动服务..."
systemctl daemon-reload
systemctl enable ${APP_NAME}
systemctl restart ${APP_NAME}
systemctl restart nginx

echo ""
echo "============================================"
echo "  部署完成!"
echo "============================================"
echo ""
echo "访问地址: http://${DOMAIN_OR_IP}"
echo ""
echo "常用命令:"
echo "  查看状态: sudo systemctl status ${APP_NAME}"
echo "  查看日志: sudo journalctl -u ${APP_NAME} -f"
echo "  重启服务: sudo systemctl restart ${APP_NAME}"
echo "  进入虚拟环境: source ${VENV_DIR}/bin/activate"
echo ""
echo "如需配置 LLM API Key, 编辑:"
echo "  sudo systemctl edit ${APP_NAME}"
echo "  添加: [Service]"
echo "  环境: Environment=\"LLM_API_KEY=your-key\""
echo ""
