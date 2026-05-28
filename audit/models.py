"""
数据库模型定义
三张核心表：Project（待审计项目）、CodeFile（代码文件）、AuditRecord（审计重构记录）
"""

from django.db import models


class Project(models.Model):
    """
    待审计项目表
    记录用户提交的每一个需要进行代码审计与重构的项目元信息
    """

    class Status(models.TextChoices):
        """项目状态枚举"""
        PENDING = "pending", "待审计"
        IN_PROGRESS = "in_progress", "审计中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "审计失败"

    name = models.CharField("项目名称", max_length=200)
    description = models.TextField("项目描述", blank=True, default="")
    repo_url = models.URLField("仓库地址", blank=True, default="")
    status = models.CharField(
        "项目状态",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    language = models.CharField("编程语言", max_length=50, default="Python")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "project"
        verbose_name = "待审计项目"
        verbose_name_plural = verbose_name
        ordering = ["-created_at"]  # 默认按创建时间倒序

    def __str__(self):
        return f"[{self.get_status_display()}] {self.name}"


class CodeFile(models.Model):
    """
    代码文件表
    存储项目中每个源代码文件的内容，用于后续的静态分析与相似度检索
    """

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="code_files",
        verbose_name="所属项目",
    )
    file_path = models.CharField("文件路径", max_length=500)
    content = models.TextField("文件内容")
    language = models.CharField("编程语言", max_length=50, default="Python")
    line_count = models.PositiveIntegerField("代码行数", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "code_file"
        verbose_name = "代码文件"
        verbose_name_plural = verbose_name
        ordering = ["file_path"]

    def save(self, *args, **kwargs):
        # 自动计算代码行数
        if self.content:
            self.line_count = len(self.content.splitlines())
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.project.name} / {self.file_path}"


class AuditRecord(models.Model):
    """
    审计重构记录表
    记录每一次代码审计的结果，包括发现的问题、修复建议和相似历史案例
    """

    class Severity(models.TextChoices):
        """问题严重程度枚举"""
        LOW = "low", "低"
        MEDIUM = "medium", "中"
        HIGH = "high", "高"
        CRITICAL = "critical", "严重"

    code_file = models.ForeignKey(
        CodeFile,
        on_delete=models.CASCADE,
        related_name="audit_records",
        verbose_name="审计文件",
    )
    issue_type = models.CharField("问题类型", max_length=100)
    description = models.TextField("问题描述")
    severity = models.CharField(
        "严重程度",
        max_length=20,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    # 原始有问题的代码片段
    original_code = models.TextField("原始代码片段")
    # Agent 给出的修复建议
    suggested_fix = models.TextField("修复建议", blank=True, default="")
    # 检索到的相似历史案例（JSON 格式存储）
    similar_cases = models.JSONField("相似历史案例", default=list, blank=True)
    # 相似度得分
    similarity_score = models.FloatField("相似度得分", default=0.0)
    is_fixed = models.BooleanField("是否已修复", default=False)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "audit_record"
        verbose_name = "审计重构记录"
        verbose_name_plural = verbose_name
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.issue_type} @ {self.code_file.file_path}"
