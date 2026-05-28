"""
DRF 序列化器

定义 API 接口的输入/输出数据格式，用于：
- 请求参数校验
- 响应数据格式化
- Django Admin 表单渲染
"""

from rest_framework import serializers
from .models import Project, CodeFile, AuditRecord


class ProjectSerializer(serializers.ModelSerializer):
    """项目序列化器"""
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    code_files_count = serializers.IntegerField(source="code_files.count", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "name", "description", "repo_url",
            "status", "status_display", "language",
            "code_files_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class CodeFileSerializer(serializers.ModelSerializer):
    """代码文件序列化器"""
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = CodeFile
        fields = [
            "id", "project", "project_name",
            "file_path", "content", "language", "line_count",
            "created_at",
        ]
        read_only_fields = ["line_count", "created_at"]


class AuditRecordSerializer(serializers.ModelSerializer):
    """审计记录序列化器"""
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    file_path = serializers.CharField(source="code_file.file_path", read_only=True)

    class Meta:
        model = AuditRecord
        fields = [
            "id", "code_file", "file_path",
            "issue_type", "description", "severity", "severity_display",
            "original_code", "suggested_fix",
            "similar_cases", "similarity_score",
            "is_fixed", "created_at",
        ]
        read_only_fields = ["created_at"]


# ============================================================
# 审计流水线专用序列化器（用于 /api/audit/ 端点）
# ============================================================

class AuditRequestSerializer(serializers.Serializer):
    """
    审计请求序列化器

    POST /api/audit/ 的请求体格式：
    {
        "code": "...",
        "file_path": "app.py",     // 可选
        "language": "Python",      // 可选
        "top_k": 3                 // 可选，相似度检索返回数量
    }
    """
    code = serializers.CharField(
        help_text="待审计的代码字符串",
        style={"base_template": "textarea.html"},
    )
    file_path = serializers.CharField(
        required=False,
        default="unknown",
        help_text="文件路径（可选）",
    )
    language = serializers.CharField(
        required=False,
        default="Python",
        help_text="编程语言（可选）",
    )
    top_k = serializers.IntegerField(
        required=False,
        default=3,
        min_value=1,
        max_value=10,
        help_text="相似度检索返回数量（1-10）",
    )


class AuditResponseSerializer(serializers.Serializer):
    """
    审计响应序列化器

    响应体格式：
    {
        "summary": "审计流水线完成 ...",
        "total_issues": 5,
        "total_duration_sec": 1.234,
        "agent_details": [...],
        "issues": [...]
    }
    """
    summary = serializers.CharField()
    total_issues = serializers.IntegerField()
    total_duration_sec = serializers.FloatField()
    agent_details = serializers.ListField(child=serializers.DictField())
    issues = serializers.ListField(child=serializers.DictField())
