"""
视图层：提供 RESTful API 接口 + 前端页面视图

第三阶段变更：
- 新增三个页面视图：dashboard / submit / projects
- 保留所有 API 接口不变
"""

import json
from datetime import datetime

import pytz
from django.db import models
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Project, CodeFile, AuditRecord
from .serializers import (
    ProjectSerializer,
    CodeFileSerializer,
    AuditRecordSerializer,
    AuditRequestSerializer,
    AuditResponseSerializer,
)
from .core.similarity import search_similar_cases
from .core.orchestrator import Orchestrator


# ============================================================
# 前端页面视图
# ============================================================

def dashboard_view(request):
    """
    仪表盘页面
    展示项目统计、问题分布、最近审计记录
    """
    total_projects = Project.objects.count()
    total_files = CodeFile.objects.count()
    total_issues = AuditRecord.objects.count()

    # 北京时间
    beijing_tz = pytz.timezone('Asia/Shanghai')
    beijing_now = datetime.now(beijing_tz)

    # 最近 10 条审计记录
    recent_records = AuditRecord.objects.select_related(
        "code_file"
    ).order_by("-created_at")[:10]

    # 严重程度分布（用于饼图）
    severity_counts = (
        AuditRecord.objects.values("severity")
        .annotate(count=models.Count("id"))
        .order_by("severity")
    )
    severity_labels = dict(AuditRecord.Severity.choices)
    severity_data = [
        {"label": severity_labels.get(s["severity"], s["severity"]), "count": s["count"]}
        for s in severity_counts
    ]

    # 问题类型 Top 10（用于柱状图）
    type_counts = (
        AuditRecord.objects.values("issue_type")
        .annotate(count=models.Count("id"))
        .order_by("-count")[:10]
    )
    type_data = [
        {"label": t["issue_type"], "count": t["count"]}
        for t in type_counts
    ]

    return render(request, "audit/dashboard.html", {
        "total_projects": total_projects,
        "total_files": total_files,
        "total_issues": total_issues,
        "beijing_now": beijing_now,
        "recent_records": recent_records,
        "severity_data": json.dumps(severity_data),
        "type_data": json.dumps(type_data),
    })


def submit_view(request):
    """
    代码提交 & 审计页面
    GET  : 显示代码提交表单
    POST : 接收代码，执行 Multi-Agent 审计，渲染结果
    """
    result = None

    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        file_path = request.POST.get("file_path", "app.py").strip()
        language = request.POST.get("language", "Python").strip()
        top_k = int(request.POST.get("top_k", 3))
        project_name = request.POST.get("project_name", "").strip()

        if code:
            # 构建上下文
            context = {
                "file_path": file_path,
                "language": language,
                "top_k": top_k,
            }

            # 执行 Multi-Agent 审计流水线
            orchestrator = Orchestrator()
            pipeline_result = orchestrator.run_pipeline(code, context)
            result = orchestrator.to_api_response(pipeline_result)

            # 保存审计结果到数据库
            _save_audit_results(code, file_path, language, result, project_name)

    return render(request, "audit/submit.html", {
        "result": result,
        "code": request.POST.get("code", "") if request.method == "POST" else "",
        "file_path": request.POST.get("file_path", "app.py") if request.method == "POST" else "app.py",
        "project_name": request.POST.get("project_name", "") if request.method == "POST" else "",
    })


def projects_view(request):
    """项目列表页面"""
    projects = Project.objects.prefetch_related("code_files").order_by("-created_at")
    return render(request, "audit/projects.html", {"projects": projects})


def detail_view(request, file_id):
    """
    审计详情页面
    展示某个代码文件的完整审计结果
    """
    code_file = get_object_or_404(CodeFile, id=file_id)
    records = AuditRecord.objects.filter(code_file=code_file).order_by("severity", "-created_at")

    # 严重程度统计
    severity_summary = (
        records.values("severity")
        .annotate(count=models.Count("id"))
        .order_by("severity")
    )
    # 补充 display name
    severity_labels = dict(AuditRecord.Severity.choices)
    for s in severity_summary:
        s["get_severity_display"] = severity_labels.get(s["severity"], s["severity"])

    return render(request, "audit/detail.html", {
        "code_file": code_file,
        "records": records,
        "severity_summary": severity_summary,
    })


def export_pdf_view(request, file_id):
    """
    导出审计报告为 PDF
    使用 xhtml2pdf 将 HTML 模板渲染为 PDF 文件下载
    """
    import logging

    logger = logging.getLogger(__name__)

    code_file = get_object_or_404(CodeFile, id=file_id)
    records = AuditRecord.objects.filter(code_file=code_file).order_by("severity", "-created_at")

    # 统计各严重程度数量
    severity_counts = dict(
        records.values_list("severity")
        .annotate(count=models.Count("id"))
        .values_list("severity", "count")
    )

    # 渲染 HTML 模板
    html_string = render_to_string("audit/pdf_report.html", {
        "code_file": code_file,
        "records": records,
        "critical_count": severity_counts.get("critical", 0),
        "high_count": severity_counts.get("high", 0),
        "medium_count": severity_counts.get("medium", 0),
        "low_count": severity_counts.get("low", 0),
    }, request=request)

    try:
        from xhtml2pdf import pisa
    except ImportError as e:
        logger.error(f"xhtml2pdf 导入失败: {e}")
        return HttpResponse(f"xhtml2pdf not installed: {e}", status=500)

    try:
        response = HttpResponse(content_type="application/pdf")
        filename = f"audit_report_{code_file.file_path.replace('/', '_').replace('.', '_')}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        pdf_status = pisa.CreatePDF(
            html_string,
            dest=response,
            encoding="utf-8",
        )

        if pdf_status.err:
            logger.error(f"PDF generation error: {pdf_status.err}")
            return HttpResponse(f"PDF generation failed: {pdf_status.err}", status=500)

        return response

    except Exception as e:
        logger.error(f"PDF export error: {e}", exc_info=True)
        return HttpResponse(f"PDF export error: {e}", status=500)


def _save_audit_results(code, file_path, language, result, project_name=""):
    """将审计结果保存到数据库"""
    try:
        # 使用用户提供的项目名称，或生成默认名称
        if not project_name:
            project_name = f"{language} 审计 - {file_path}"

        # 获取或创建项目（按名称查找，不存在则创建）
        project, _ = Project.objects.get_or_create(
            name=project_name,
            defaults={
                "description": f"文件: {file_path}",
                "status": Project.Status.COMPLETED,
                "language": language,
            },
        )

        # 创建代码文件记录
        code_file = CodeFile.objects.create(
            project=project,
            file_path=file_path,
            content=code,
            language=language,
        )

        # 保存每条审计记录
        for issue in result.get("issues", []):
            AuditRecord.objects.create(
                code_file=code_file,
                issue_type=issue.get("issue_type", "unknown"),
                description=issue.get("description", ""),
                severity=issue.get("severity", "medium"),
                original_code=issue.get("original_code", ""),
                suggested_fix=issue.get("suggested_fix", ""),
                similarity_score=issue.get("similarity_score", 0.0),
                is_fixed=False,
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"保存审计结果失败: {e}")


# ============================================================
# RESTful API 接口（与第二阶段一致）
# ============================================================

class ProjectViewSet(viewsets.ModelViewSet):
    """项目管理 API：支持增删改查"""
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer


class CodeFileViewSet(viewsets.ModelViewSet):
    """代码文件管理 API"""
    queryset = CodeFile.objects.all()
    serializer_class = CodeFileSerializer


class AuditRecordViewSet(viewsets.ModelViewSet):
    """审计记录管理 API"""
    queryset = AuditRecord.objects.all()
    serializer_class = AuditRecordSerializer


@api_view(["POST"])
def audit_code_api(request):
    """
    POST /api/audit/
    触发完整的 Multi-Agent 代码审计流水线
    """
    req_serializer = AuditRequestSerializer(data=request.data)
    if not req_serializer.is_valid():
        return Response(
            {"error": "请求参数无效", "details": req_serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    validated = req_serializer.validated_data
    code = validated["code"]

    context = {
        "file_path": validated.get("file_path", "unknown"),
        "language": validated.get("language", "Python"),
        "top_k": validated.get("top_k", 3),
    }

    orchestrator = Orchestrator()
    pipeline_result = orchestrator.run_pipeline(code, context)
    response_data = orchestrator.to_api_response(pipeline_result)

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(["POST"])
def search_similar_api(request):
    """
    POST /api/search-similar/
    接收代码片段，返回相似的历史修复案例
    """
    code_snippet = request.data.get("code_snippet", "")
    top_k = request.data.get("top_k", 3)
    use_db = request.data.get("use_db", True)

    if not code_snippet:
        return Response(
            {"error": "code_snippet 不能为空"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    results = search_similar_cases(code_snippet, top_k=top_k, use_db=use_db)

    return Response({
        "query": code_snippet[:200],
        "total": len(results),
        "results": results,
    })
