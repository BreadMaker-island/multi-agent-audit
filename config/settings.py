"""
Django 项目配置文件
基于 Multi-Agent 架构的自动化代码重构与安全审计系统
"""

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 安全密钥（生产环境通过环境变量 DJANGO_SECRET_KEY 设置）
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-this-in-production-env",
)

# 调试模式（生产环境通过环境变量 DJANGO_DEBUG=False 关闭）
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

# 允许的主机（生产环境通过环境变量 DJANGO_ALLOWED_HOSTS 设置，逗号分隔）
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

# ============================================================
# 已安装的应用
# ============================================================
INSTALLED_APPS = [
    # Django 内置应用
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 第三方应用
    "rest_framework",  # Django REST Framework，用于构建 API
    # 自定义应用
    "audit.apps.AuditConfig",  # 审计子应用
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ============================================================
# 数据库配置（开发阶段使用 SQLite，生产环境切换为 PostgreSQL）
# ============================================================
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ============================================================
# 国际化与时区（中国大陆）
# ============================================================
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# ============================================================
# 静态文件与媒体文件
# ============================================================
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ============================================================
# Django REST Framework 配置
# ============================================================
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",  # 演示阶段开放权限
    ],
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================================
# LLM 配置（小米 MiMo，Anthropic 兼容接口）
# ============================================================
LLM_CONFIG = {
    # 提供商：mimo（小米MiMo）/ deepseek / openai / qwen
    "provider": "mimo",

    # API Key（通过环境变量 LLM_API_KEY 设置，或直接填入）
    "api_key": os.environ.get("LLM_API_KEY", ""),

    # MiMo 的 Anthropic 兼容端点
    "base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
    "model": "mimo-v2.5-pro",
}

# ============================================================
# 生产环境安全配置
# ============================================================
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL", "False").lower() in ("true", "1")
