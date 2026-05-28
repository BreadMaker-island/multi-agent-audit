"""
管理命令：将种子历史案例导入数据库

用法：
    python manage.py seed_cases

执行后会将 similarity.py 中的 8 个硬编码案例写入 AuditRecord 表，
作为系统启动时的初始案例库，供相似度检索使用。
"""

from django.core.management.base import BaseCommand
from audit.models import Project, CodeFile, AuditRecord
from audit.core.similarity import _SEED_CASES


class Command(BaseCommand):
    help = "将种子历史案例导入数据库，作为相似度检索的初始案例库"

    def handle(self, *args, **options):
        # 创建一个占位项目和代码文件（外键依赖）
        project, _ = Project.objects.get_or_create(
            name="种子案例库",
            defaults={
                "description": "系统内置的历史修复案例，用于相似度检索",
                "status": Project.Status.COMPLETED,
                "language": "Python",
            },
        )

        code_file, _ = CodeFile.objects.get_or_create(
            project=project,
            file_path="seed_cases.py",
            defaults={
                "content": "# 种子案例库占位文件",
                "language": "Python",
            },
        )

        created_count = 0
        for case in _SEED_CASES:
            _, created = AuditRecord.objects.get_or_create(
                code_file=code_file,
                issue_type=case["issue_type"],
                original_code=case["original_code"],
                defaults={
                    "description": case["description"],
                    "suggested_fix": case["suggested_fix"],
                    "severity": "high",
                    "is_fixed": True,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f"  + {case['issue_type']}")
            else:
                self.stdout.write(f"  = {case['issue_type']} (已存在，跳过)")

        self.stdout.write(self.style.SUCCESS(
            f"\n完成！新增 {created_count} 条种子案例，"
            f"数据库中共有 {AuditRecord.objects.filter(is_fixed=True).count()} 条可检索案例"
        ))
