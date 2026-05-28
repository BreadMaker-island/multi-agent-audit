"""
安全审计 Agent

职责：使用 bandit 对代码进行静态安全扫描，识别常见安全漏洞。

bandit 是 Python 官方社区推荐的安全扫描工具，能检测：
- 硬编码密码 / 密钥
- SQL 注入风险
- 不安全的反序列化（pickle.loads）
- 不安全的随机数生成（random 模块）
- XSS 风险
- 路径遍历
- 弱加密算法（MD5, SHA1）
等 200+ 种安全问题模式
"""

import tempfile
import os
import json
import logging
from typing import Any, Dict

from .base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

# bandit 严重程度 → 我们系统的严重程度映射
_SEVERITY_MAP = {
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "UNDEFINED": "medium",
}


class SecurityAgent(BaseAgent):
    """
    安全审计 Agent

    工作流程：
    ① 将代码写入临时 .py 文件
    ② 调用 bandit 的 Python API 进行扫描
    ③ 解析 bandit 的 JSON 输出，转换为 AgentResult
    """

    def __init__(self):
        super().__init__(name="SecurityAgent")

    def execute(self, code: str, context: Dict[str, Any]) -> AgentResult:
        """
        执行安全扫描

        Args:
            code    : 待扫描的 Python 代码字符串
            context : 可选上下文，支持 'file_path' 键

        Returns:
            AgentResult，issues 中每个元素包含：
            - issue_type  : 安全问题类型（如 B101, B602）
            - severity    : 严重程度（low / medium / high / critical）
            - description : 问题描述
            - line_number : 问题所在行号
            - original_code : 原始代码片段
            - suggested_fix : bandit 建议的修复方式
            - cwe_id      : CWE 漏洞编号
        """
        issues = []

        # ----------------------------------------------------------
        # 步骤 1：将代码写入临时文件（bandit 需要文件路径作为输入）
        # ----------------------------------------------------------
        tmp_file = None
        try:
            tmp_file = tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False,
                encoding="utf-8",
            )
            tmp_file.write(code)
            tmp_file.close()

            # ----------------------------------------------------------
            # 步骤 2：调用 bandit Python API 扫描
            # ----------------------------------------------------------
            from bandit.core import config as bandit_config
            from bandit.core import manager as bandit_manager

            # 初始化 bandit 配置
            b_conf = bandit_config.BanditConfig()
            # 创建 bandit 管理器，设置扫描目标和配置
            b_mgr = bandit_manager.BanditManager(b_conf, "file")
            b_mgr.discover_files([tmp_file.name])
            b_mgr.run_tests()

            # ----------------------------------------------------------
            # 步骤 3：解析扫描结果，转换为统一的 AgentResult
            # ----------------------------------------------------------
            for result in b_mgr.get_issue_list():
                severity_str = str(result.severity).upper()
                severity = _SEVERITY_MAP.get(severity_str, "medium")

                # bandit 的 CONFIDENCE 高于 MEDIUM 才计入
                confidence = str(result.confidence).upper()
                if confidence not in ("HIGH", "MEDIUM"):
                    continue

                # 提取问题代码片段
                original = self._extract_code_snippet(code, result.lineno)

                issues.append({
                    "issue_type": result.test_id,       # 如 B101, B602
                    "severity": severity,
                    "description": result.text,          # bandit 给出的描述
                    "line_number": result.lineno,
                    "original_code": original,
                    "suggested_fix": self._get_fix_suggestion(result.test_id),
                    "cwe_id": getattr(getattr(result, "cwe", None), "id", ""),
                })

            summary = f"安全扫描完成，发现 {len(issues)} 个安全问题"

        except ImportError:
            logger.warning("bandit 未安装，安全扫描 Agent 降级为模式匹配模式")
            issues = self._fallback_pattern_scan(code)
            summary = f"安全扫描完成（降级模式），发现 {len(issues)} 个安全问题"

        finally:
            # 清理临时文件
            if tmp_file and os.path.exists(tmp_file.name):
                os.unlink(tmp_file.name)

        return AgentResult(
            agent_name=self.name,
            success=True,
            issues=issues,
            summary=summary,
            details={"total_issues": len(issues)},
        )

    # ----------------------------------------------------------
    # 辅助方法
    # ----------------------------------------------------------

    @staticmethod
    def _extract_code_snippet(code: str, lineno: int, context_lines: int = 2) -> str:
        """从代码中提取问题行及上下文"""
        lines = code.splitlines()
        start = max(0, lineno - 1 - context_lines)
        end = min(len(lines), lineno + context_lines)
        return "\n".join(lines[start:end])

    @staticmethod
    def _get_fix_suggestion(test_id: str) -> str:
        """根据 bandit 测试 ID 返回修复建议"""
        suggestions = {
            "B101": "不要使用 assert 语句做安全校验，assert 在 -O 模式下会被移除",
            "B102": "避免使用 exec()，存在代码注入风险",
            "B103": "不要设置过于宽松的文件权限（如 0o777），应使用 0o600 或 0o644",
            "B104": "绑定到所有网络接口（0.0.0.0）存在安全风险，生产环境应指定具体接口",
            "B105": "硬编码密码，应从环境变量或密钥管理服务读取",
            "B106": "硬编码密码，应从环境变量或密钥管理服务读取",
            "B107": "硬编码密码，应从环境变量或密钥管理服务读取",
            "B108": "使用不安全的临时文件路径，应使用 tempfile 模块",
            "B110": "使用 try-except-pass 会吞掉所有异常，应至少记录日志",
            "B112": "使用 try-except-continue 会跳过异常处理",
            "B201": "使用 Flask 应用调试模式存在安全风险，生产环境应关闭",
            "B301": "使用 pickle 反序列化不可信数据可导致远程代码执行，改用 json",
            "B302": "使用 marshal 反序列化不可信数据",
            "B303": "使用不安全的哈希算法（MD5/SHA1），应使用 SHA256 或更高",
            "B304": "使用不安全的密码哈希算法，应使用 bcrypt 或 argon2",
            "B305": "使用不安全的 cipher 模式",
            "B306": "使用 markupsafe.escape 替代 mktemp",
            "B307": "使用 ast.literal_eval 替代 eval()",
            "B308": "使用 markupsafe.escape 替代 markupsafe.Markup",
            "B309": "使用 secrets.compare_digest 替代 == 进行密钥比较",
            "B310": "验证 URL 的 scheme 防止 file:// 等协议注入",
            "B311": "使用 secrets 模块替代 random 模块生成安全令牌",
            "B312": "使用 http.client 替代 telnetlib",
            "B313": "使用 xml.etree.ElementTree 替代 xml.dom.minidom",
            "B314": "使用 xml.etree.ElementTree 替代 xml.sax",
            "B315": "使用 xml.etree.ElementTree 替代 xml.expat",
            "B316": "使用 xml.etree.ElementTree 替代 xml.dom.minidom",
            "B317": "使用 xml.etree.ElementTree 替代 xml.sax",
            "B318": "使用 defusedxml 替代 xml.dom.minidom 解析不可信 XML",
            "B319": "使用 defusedxml 替代 xml.sax 解析不可信 XML",
            "B320": "使用 defusedxml 替代 xml.expat 解析不可信 XML",
            "B321": "使用 ftplib 替代 ftplib.FTP",
            "B323": "在 requests 中 verify=False 会禁用 SSL 证书验证",
            "B324": "使用 hashlib.sha256 替代 hashlib.md5",
            "B325": "使用 tempfile 模块替代 tempfile.mktemp",
            "B401": "导入 telnetlib 存在安全风险",
            "B402": "导入 ftplib 存在安全风险",
            "B403": "导入 pickle 存在安全风险",
            "B404": "导入 subprocess 存在安全风险",
            "B405": "导入 xml.etree.ElementTree 存在 XML 注入风险",
            "B406": "导入 xml.sax 存在 XML 注入风险",
            "B407": "导入 xml.expat 存在 XML 注入风险",
            "B408": "导入 xml.minidom 存在 XML 注入风险",
            "B409": "导入 xml.dom.minidom 存在 XML 注入风险",
            "B410": "导入 lxml 存在安全风险",
            "B411": "导入 xmlrpclib 存在安全风险",
            "B412": "导入 httpoxy 存在安全风险",
            "B501": "使用 requests 时应设置 SSL 证书验证",
            "B502": "使用 ssl 模块时应验证证书",
            "B503": "使用 ssl 模块时应禁用 SSLv2/SSLv3",
            "B504": "使用 ssl 模块时应设置密码套件",
            "B505": "使用 cryptography 模块时应使用安全的密钥长度",
            "B506": "使用 yaml.load() 存在安全风险，应使用 yaml.safe_load()",
            "B507": "使用 ssh 模块时应验证主机密钥",
            "B601": "使用 paramiko 时存在命令注入风险",
            "B602": "使用 subprocess.call(shell=True) 存在命令注入风险，应使用列表参数",
            "B603": "使用 subprocess.call() 时应设置 shell=False",
            "B604": "使用 subprocess.call() 时应设置 shell=False",
            "B605": "使用 os.system() 存在命令注入风险，应使用 subprocess",
            "B606": "使用 os.popen() 存在命令注入风险，应使用 subprocess",
            "B607": "使用 os.startfile() 存在安全风险",
            "B608": "使用 SQL 拼接存在 SQL 注入风险，应使用参数化查询",
            "B609": "使用 wildcard 模式导入存在安全风险",
            "B610": "使用 Django 的 extra() 存在 SQL 注入风险",
            "B611": "使用 Django 的 raw() 存在 SQL 注入风险",
            "B701": "使用 jinja2 模板时应开启 autoescape",
            "B702": "使用 Mako 模板时应使用转义",
            "B703": "使用 Django 模板时应开启自动转义",
        }
        return suggestions.get(test_id, "请参考 bandit 官方文档获取修复建议")

    def _fallback_pattern_scan(self, code: str) -> list:
        """
        降级模式：当 bandit 未安装时，使用正则表达式做简单模式匹配
        覆盖最常见的 5 类安全问题
        """
        import re
        issues = []
        patterns = [
            {
                "pattern": r'execute\s*\(\s*["\'][^"\']*(?:SELECT|INSERT|UPDATE|DELETE).*["\']?\s*\+',
                "issue_type": "B608",
                "severity": "high",
                "description": "SQL 字符串拼接，存在 SQL 注入风险",
            },
            {
                "pattern": r'pickle\.loads?\s*\(',
                "issue_type": "B301",
                "severity": "high",
                "description": "使用 pickle 反序列化，存在远程代码执行风险",
            },
            {
                "pattern": r'(?i)(?:password|secret_key|api_key|token)\s*=\s*["\'][^"\']{3,}["\']',
                "issue_type": "B105",
                "severity": "medium",
                "description": "硬编码密码/密钥，应从环境变量读取",
            },
            {
                "pattern": r'random\.(randint|choice|random)\s*\(',
                "issue_type": "B311",
                "severity": "medium",
                "description": "使用 random 模块生成安全令牌，应使用 secrets 模块",
            },
            {
                "pattern": r'eval\s*\(',
                "issue_type": "B307",
                "severity": "high",
                "description": "使用 eval() 存在代码注入风险，应使用 ast.literal_eval()",
            },
        ]

        lines = code.splitlines()
        for i, line in enumerate(lines, 1):
            for p in patterns:
                if re.search(p["pattern"], line):
                    issues.append({
                        "issue_type": p["issue_type"],
                        "severity": p["severity"],
                        "description": p["description"],
                        "line_number": i,
                        "original_code": line.strip(),
                        "suggested_fix": self._get_fix_suggestion(p["issue_type"]),
                        "cwe_id": "",
                    })

        return issues
