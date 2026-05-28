"""
Django Admin 后台配置
注册三张核心表，方便在管理后台直接查看和操作数据
"""

from django.contrib import admin
from .models import Project, CodeFile, AuditRecord


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "language", "status", "created_at")
    list_filter = ("status", "language")
    search_fields = ("name", "description")


@admin.register(CodeFile)
class CodeFileAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "file_path", "language", "line_count")
    list_filter = ("language",)
    search_fields = ("file_path", "content")


@admin.register(AuditRecord)
class AuditRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "code_file", "issue_type", "severity", "is_fixed", "created_at")
    list_filter = ("severity", "is_fixed", "issue_type")
    search_fields = ("description", "original_code")
