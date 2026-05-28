# Gunicorn 配置文件
# 用法: gunicorn config.wsgi:application -c gunicorn.conf.py

import multiprocessing

# 绑定地址
bind = "127.0.0.1:8000"

# Worker 数量 (CPU 核心数 * 2 + 1)
workers = multiprocessing.cpu_count() * 2 + 1

# Worker 类型
worker_class = "sync"

# 超时时间 (秒)
timeout = 300

# 最大请求数 (处理这么多请求后重启 worker, 防止内存泄漏)
max_requests = 1000
max_requests_jitter = 50

# 日志
accesslog = "-"
errorlog = "-"
loglevel = "info"

# 进程名
proc_name = "multi_agent_audit"
