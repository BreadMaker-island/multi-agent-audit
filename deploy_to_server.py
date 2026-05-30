# -*- coding: utf-8 -*-
"""
一键部署脚本 - 将项目部署到远程服务器
"""

import paramiko
import os
import sys
import time
from scp import SCPClient

# Windows 控制台 UTF-8 支持
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 配置信息
SERVER_IP = "39.105.134.23"
SSH_USER = "root"
SSH_PASSWORD = "Ji2693964451"
APP_NAME = "multi-agent-audit"
REMOTE_DIR = f"/opt/{APP_NAME}"
LLM_API_KEY = "tp-c1ngsuvob45ykvmmrsfmbja67wfu1go5uzitl5fptjm8a13b"
LLM_PROVIDER = "mimo"
LLM_MODEL = "mimo-v2.5-pro"

# 本地项目目录
LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))

# 排除的文件和目录
EXCLUDE_PATTERNS = [
    '.git',
    '__pycache__',
    '*.pyc',
    'db.sqlite3',
    'venv',
    'staticfiles',
    '.env',
    'deploy_to_server.py',
    '*.docx',
]


def create_ssh_client():
    """创建 SSH 客户端"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=SERVER_IP,
        username=SSH_USER,
        password=SSH_PASSWORD,
        timeout=30
    )
    return client


def execute_command(client, command, sudo=False):
    """执行远程命令"""
    if sudo:
        command = f"sudo {command}"
    print(f"  执行: {command[:80]}...")
    stdin, stdout, stderr = client.exec_command(command)
    exit_code = stdout.channel.recv_exit_status()
    output = stdout.read().decode('utf-8', errors='ignore')
    error = stderr.read().decode('utf-8', errors='ignore')
    return exit_code, output, error


def should_exclude(path):
    """检查文件是否应该排除"""
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith('*'):
            if path.endswith(pattern[1:]):
                return True
        elif pattern in path.split(os.sep):
            return True
    return False


def upload_project(client):
    """上传项目文件"""
    print("\n[1/6] 上传项目文件...")

    # 创建远程目录
    execute_command(client, f"mkdir -p {REMOTE_DIR}", sudo=True)

    # 使用 SCP 上传
    with SCPClient(client.get_transport()) as scp:
        for root, dirs, files in os.walk(LOCAL_DIR):
            # 过滤排除的目录
            dirs[:] = [d for d in dirs if not should_exclude(d)]

            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, LOCAL_DIR)

                if should_exclude(relative_path):
                    continue

                remote_path = os.path.join(REMOTE_DIR, relative_path)
                remote_dir = os.path.dirname(remote_path)

                # 创建远程目录
                execute_command(client, f"mkdir -p {remote_dir}", sudo=True)

                # 上传文件
                print(f"  上传: {relative_path}")
                scp.put(local_path, remote_path)

    # 设置权限
    execute_command(client, f"chown -R www-data:www-data {REMOTE_DIR}", sudo=True)
    execute_command(client, f"chmod -R 755 {REMOTE_DIR}", sudo=True)
    print("  ✓ 文件上传完成")


def install_dependencies(client):
    """安装系统依赖"""
    print("\n[2/6] 安装系统依赖...")

    commands = [
        "apt-get update -qq",
        "apt-get install -y -qq python3 python3-pip python3-venv nginx",
    ]

    for cmd in commands:
        exit_code, output, error = execute_command(client, cmd, sudo=True)
        if exit_code != 0 and "already installed" not in error:
            print(f"  ⚠ 警告: {error[:100]}")
        else:
            print(f"  ✓ 完成")

    print("  ✓ 系统依赖安装完成")


def setup_virtualenv(client):
    """创建虚拟环境并安装依赖"""
    print("\n[3/6] 创建虚拟环境并安装依赖...")

    venv_dir = f"{REMOTE_DIR}/venv"

    commands = [
        f"python3 -m venv {venv_dir}",
        f"{venv_dir}/bin/pip install -q --upgrade pip",
        f"{venv_dir}/bin/pip install -q -r {REMOTE_DIR}/requirements.txt",
        f"{venv_dir}/bin/pip install -q gunicorn",
    ]

    for cmd in commands:
        exit_code, output, error = execute_command(client, cmd, sudo=True)
        if exit_code != 0:
            print(f"  ⚠ 警告: {error[:100]}")
        else:
            print(f"  ✓ 完成")

    print("  ✓ 虚拟环境创建完成")


def configure_environment(client):
    """配置环境变量"""
    print("\n[4/6] 配置环境变量...")

    # 生成 Django SECRET KEY
    exit_code, output, _ = execute_command(
        client,
        f"{REMOTE_DIR}/venv/bin/python3 -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\"",
        sudo=True
    )
    secret_key = output.strip() if exit_code == 0 else "change-this-to-a-random-secret-key"

    # 创建 .env 文件
    env_content = f"""DJANGO_SECRET_KEY={secret_key}
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS={SERVER_IP},localhost,127.0.0.1
LLM_API_KEY={LLM_API_KEY}
LLM_PROVIDER={LLM_PROVIDER}
LLM_MODEL={LLM_MODEL}
"""

    # 写入 .env 文件
    execute_command(client, f"cat > {REMOTE_DIR}/.env << 'EOF'\n{env_content}EOF", sudo=True)
    execute_command(client, f"chmod 600 {REMOTE_DIR}/.env", sudo=True)
    execute_command(client, f"chown www-data:www-data {REMOTE_DIR}/.env", sudo=True)

    print("  ✓ 环境变量配置完成")


def init_database(client):
    """初始化数据库"""
    print("\n[5/6] 初始化数据库...")

    commands = [
        f"cd {REMOTE_DIR} && DJANGO_DEBUG=False DJANGO_SECRET_KEY=$(grep DJANGO_SECRET_KEY {REMOTE_DIR}/.env | cut -d= -f2) DJANGO_ALLOWED_HOSTS={SERVER_IP},localhost {REMOTE_DIR}/venv/bin/python manage.py migrate --run-syncdb",
        f"cd {REMOTE_DIR} && DJANGO_DEBUG=False {REMOTE_DIR}/venv/bin/python manage.py collectstatic --noinput",
        f"cd {REMOTE_DIR} && DJANGO_DEBUG=False {REMOTE_DIR}/venv/bin/python manage.py seed_cases",
    ]

    for cmd in commands:
        exit_code, output, error = execute_command(client, cmd, sudo=True)
        if exit_code != 0:
            print(f"  ⚠ 警告: {error[:100]}")
        else:
            print(f"  ✓ 完成")

    print("  ✓ 数据库初始化完成")


def configure_services(client):
    """配置 systemd 和 Nginx"""
    print("\n[6/6] 配置服务...")

    venv_dir = f"{REMOTE_DIR}/venv"

    # 读取 .env 中的 SECRET KEY
    exit_code, output, _ = execute_command(
        client,
        f"grep DJANGO_SECRET_KEY {REMOTE_DIR}/.env | cut -d= -f2",
        sudo=True
    )
    secret_key = output.strip() if exit_code == 0 else "change-this"

    # systemd 服务文件
    service_content = f"""[Unit]
Description=Multi-Agent Code Audit System
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory={REMOTE_DIR}
Environment="DJANGO_DEBUG=False"
Environment="DJANGO_SECRET_KEY={secret_key}"
Environment="DJANGO_ALLOWED_HOSTS={SERVER_IP},localhost"
Environment="LLM_API_KEY={LLM_API_KEY}"
Environment="LLM_PROVIDER={LLM_PROVIDER}"
Environment="LLM_MODEL={LLM_MODEL}"
ExecStart={venv_dir}/bin/gunicorn config.wsgi:application -c gunicorn.conf.py
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

    execute_command(client, f"cat > /etc/systemd/system/{APP_NAME}.service << 'EOF'\n{service_content}EOF", sudo=True)

    # Nginx 配置
    nginx_content = f"""server {{
    listen 80;
    server_name {SERVER_IP};

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    location /static/ {{
        alias {REMOTE_DIR}/staticfiles/;
        expires 30d;
    }}

    location /media/ {{
        alias {REMOTE_DIR}/media/;
        expires 7d;
    }}

    location / {{
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 300;
        proxy_read_timeout 300;
        proxy_send_timeout 300;
    }}

    client_max_body_size 10M;
}}
"""

    execute_command(client, f"cat > /etc/nginx/sites-available/{APP_NAME} << 'EOF'\n{nginx_content}EOF", sudo=True)
    execute_command(client, f"ln -sf /etc/nginx/sites-available/{APP_NAME} /etc/nginx/sites-enabled/", sudo=True)
    execute_command(client, "rm -f /etc/nginx/sites-enabled/default", sudo=True)

    # 设置权限
    execute_command(client, f"chown -R www-data:www-data {REMOTE_DIR}", sudo=True)
    execute_command(client, f"chmod -R 755 {REMOTE_DIR}", sudo=True)

    # 启动服务
    execute_command(client, "systemctl daemon-reload", sudo=True)
    execute_command(client, f"systemctl enable {APP_NAME}", sudo=True)
    execute_command(client, f"systemctl restart {APP_NAME}", sudo=True)
    execute_command(client, "systemctl restart nginx", sudo=True)

    print("  ✓ 服务配置完成")


def check_service_status(client):
    """检查服务状态"""
    print("\n检查服务状态...")

    exit_code, output, _ = execute_command(
        client,
        f"systemctl is-active {APP_NAME}",
        sudo=True
    )
    app_status = "✓ 运行中" if exit_code == 0 else "✗ 未运行"

    exit_code, output, _ = execute_command(
        client,
        "systemctl is-active nginx",
        sudo=True
    )
    nginx_status = "✓ 运行中" if exit_code == 0 else "✗ 未运行"

    print(f"  应用服务: {app_status}")
    print(f"  Nginx:    {nginx_status}")


def main():
    """主函数"""
    print("=" * 50)
    print("  Multi-Agent 代码审计系统 - 一键部署")
    print("=" * 50)
    print(f"目标服务器: {SERVER_IP}")
    print(f"应用目录:   {REMOTE_DIR}")
    print()

    try:
        # 创建 SSH 连接
        print("正在连接服务器...")
        client = create_ssh_client()
        print("✓ SSH 连接成功")

        # 执行部署步骤
        upload_project(client)
        install_dependencies(client)
        setup_virtualenv(client)
        configure_environment(client)
        init_database(client)
        configure_services(client)
        check_service_status(client)

        print("\n" + "=" * 50)
        print("  部署完成!")
        print("=" * 50)
        print(f"\n访问地址: http://{SERVER_IP}")
        print("\n常用命令:")
        print(f"  查看状态: ssh {SSH_USER}@{SERVER_IP} 'sudo systemctl status {APP_NAME}'")
        print(f"  查看日志: ssh {SSH_USER}@{SERVER_IP} 'sudo journalctl -u {APP_NAME} -f'")
        print(f"  重启服务: ssh {SSH_USER}@{SERVER_IP} 'sudo systemctl restart {APP_NAME}'")

        # 关闭连接
        client.close()

    except Exception as e:
        print(f"\n✗ 部署失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
