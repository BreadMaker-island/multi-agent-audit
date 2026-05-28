"""
审计子应用的 URL 路由

第三阶段新增：
- / 仪表盘
- /submit/ 代码提交 & 审计
- /projects/ 项目列表
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

# DRF 路由器：自动生成 ViewSet 的 URL
router = DefaultRouter()
router.register(r"projects", views.ProjectViewSet)
router.register(r"code-files", views.CodeFileViewSet)
router.register(r"audit-records", views.AuditRecordViewSet)

urlpatterns = [
    # 前端页面路由
    path("", views.dashboard_view, name="dashboard"),
    path("submit/", views.submit_view, name="submit"),
    path("projects/", views.projects_view, name="projects"),
    path("detail/<int:file_id>/", views.detail_view, name="detail"),
    path("export-pdf/<int:file_id>/", views.export_pdf_view, name="export-pdf"),
    # API 路由
    path("api/", include(router.urls)),
    path("api/audit/", views.audit_code_api, name="audit-code"),
    path("api/search-similar/", views.search_similar_api, name="search-similar"),
]
