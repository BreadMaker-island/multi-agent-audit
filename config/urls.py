"""
根 URL 配置

第三阶段变更：
- / 指向 audit 子应用的页面路由（仪表盘）
- /admin/ 指向 Django Admin
- 所有 API 路由由 audit 子应用管理
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("audit.urls")),  # 页面 + API 统一由 audit 管理
]
