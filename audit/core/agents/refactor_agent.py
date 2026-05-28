"""
代码重构建议 Agent（第四阶段：LLM 增强版）

分析策略：
① 优先使用 LLM（小米 MiMo-7B）进行智能分析
② LLM 不可用时，自动降级为规则引擎（AST + 正则匹配）
③ 两种模式的输出格式完全一致，对 Orchestrator 透明
"""

import re
import ast
import logging
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)


class RefactorAgent(BaseAgent):
    """
    代码重构建议 Agent

    工作流程：
    ① 尝试调用 LLM 进行智能代码分析
    ② 若 LLM 不可用（未配置 / 调用失败），降级为规则引擎
    ③ 返回统一格式的 AgentResult
    """

    def __init__(self):
        super().__init__(name="RefactorAgent")

    def execute(self, code: str, context: Dict[str, Any]) -> AgentResult:
        """
        执行代码质量分析

        Args:
            code    : 待分析的 Python 代码字符串
            context : 可选上下文，支持 'language' 键

        Returns:
            AgentResult
        """
        # ----------------------------------------------------------
        # 策略 1：尝试 LLM 智能分析
        # ----------------------------------------------------------
        llm_result = self._try_llm_analysis(code, context)
        if llm_result is not None:
            return llm_result

        # ----------------------------------------------------------
        # 策略 2：降级为规则引擎
        # ----------------------------------------------------------
        logger.info("LLM 不可用，降级为规则引擎分析")
        return self._rule_based_analysis(code)

    # ==========================================================
    # LLM 智能分析
    # ==========================================================

    def _try_llm_analysis(self, code: str, context: Dict[str, Any]):
        """
        尝试使用 LLM 分析代码

        Returns:
            AgentResult 如果成功，None 如果 LLM 不可用
        """
        try:
            from ..llm_client import LLMClient

            client = LLMClient()

            # 检查 API Key 是否配置
            if not client.api_key:
                print("[RefactorAgent] API Key 未配置，降级为规则引擎")
                return None

            print(f"[RefactorAgent] 正在调用 {client.provider_name} ({client.model}) ...")
            llm_issues = client.analyze_code(code, context)

            if llm_issues is None:
                print("[RefactorAgent] LLM 返回 None，降级为规则引擎")
                return None

            print(f"[RefactorAgent] LLM 分析成功，返回 {len(llm_issues)} 个问题")

            # 标准化 LLM 返回的问题格式
            issues = []
            for item in llm_issues:
                issues.append({
                    "issue_type": item.get("issue_type", "llm_suggestion"),
                    "severity": item.get("severity", "medium"),
                    "description": item.get("description", ""),
                    "line_number": item.get("line_number", 0),
                    "original_code": item.get("original_code", ""),
                    "suggested_fix": item.get("suggested_fix", ""),
                    "source": "llm",
                })

            summary = (
                f"LLM 智能分析完成（{client.provider_name}），"
                f"发现 {len(issues)} 个可改进项"
            )

            return AgentResult(
                agent_name=self.name,
                success=True,
                issues=issues,
                summary=summary,
                details={
                    "total_issues": len(issues),
                    "analysis_mode": "llm",
                    "provider": client.provider_name,
                },
            )

        except Exception as e:
            logger.warning(f"LLM 分析异常，将降级为规则引擎: {e}")
            return None

    # ==========================================================
    # 规则引擎分析（降级方案）
    # ==========================================================

    def _rule_based_analysis(self, code: str) -> AgentResult:
        """规则引擎分析，与第三阶段逻辑一致"""
        issues = []

        ast_issues = self._analyze_ast(code)
        issues.extend(ast_issues)

        pattern_issues = self._analyze_patterns(code)
        issues.extend(pattern_issues)

        line_issues = self._analyze_line_level(code)
        issues.extend(line_issues)

        for issue in issues:
            issue["source"] = "rule"

        summary = f"规则引擎分析完成，发现 {len(issues)} 个可改进项"

        return AgentResult(
            agent_name=self.name,
            success=True,
            issues=issues,
            summary=summary,
            details={
                "total_issues": len(issues),
                "analysis_mode": "rule",
            },
        )

    # ----------------------------------------------------------
    # AST 结构分析
    # ----------------------------------------------------------

    def _analyze_ast(self, code: str) -> List[Dict[str, Any]]:
        """使用 Python AST 分析代码结构"""
        issues = []

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            issues.append({
                "issue_type": "syntax_error",
                "severity": "high",
                "description": f"代码存在语法错误: {e}",
                "line_number": getattr(e, "lineno", 0),
                "original_code": "",
                "suggested_fix": "请修正语法错误后重新分析",
            })
            return issues

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_lines = self._count_lines(node)
                if func_lines > 50:
                    issues.append({
                        "issue_type": "complexity",
                        "severity": "medium",
                        "description": f"函数 '{node.name}' 过长（{func_lines} 行），建议拆分为更小的函数",
                        "line_number": node.lineno,
                        "original_code": f"def {node.name}(...):  # 共 {func_lines} 行",
                        "suggested_fix": f"将 '{node.name}' 拆分为 2-3 个职责单一的子函数",
                    })

                arg_count = len(node.args.args) + len(node.args.kwonlyargs)
                if arg_count > 5:
                    issues.append({
                        "issue_type": "complexity",
                        "severity": "low",
                        "description": f"函数 '{node.name}' 参数过多（{arg_count} 个），建议封装为对象",
                        "line_number": node.lineno,
                        "original_code": f"def {node.name}({', '.join(a.arg for a in node.args.args)}):",
                        "suggested_fix": f"将参数封装为 dataclass 或 dict，降低函数签名复杂度",
                    })

        return issues

    # ----------------------------------------------------------
    # 模式匹配分析
    # ----------------------------------------------------------

    def _analyze_patterns(self, code: str) -> List[Dict[str, Any]]:
        """基于正则表达式的模式匹配分析"""
        issues = []
        lines = code.splitlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if re.match(r"except\s*:", stripped):
                issues.append({
                    "issue_type": "best_practice",
                    "severity": "medium",
                    "description": "使用了裸 except（不指定异常类型），会捕获所有异常包括 KeyboardInterrupt",
                    "line_number": i,
                    "original_code": stripped,
                    "suggested_fix": "改为 except Exception as e: 并记录日志",
                })

            magic_numbers = re.findall(
                r"(?<!\w)(\d{2,})(?!\w*(?:%|px|em|rem|s|ms))", stripped
            )
            safe_numbers = {"0", "1", "2", "10", "100", "200", "204", "301", "302", "400", "401", "403", "404", "500"}
            for num in magic_numbers:
                if num not in safe_numbers and not stripped.startswith("#"):
                    if not re.match(r"^[A-Z_]+\s*=", stripped):
                        issues.append({
                            "issue_type": "naming",
                            "severity": "low",
                            "description": f"发现魔法数字 {num}，建议提取为命名常量以提高可读性",
                            "line_number": i,
                            "original_code": stripped,
                            "suggested_fix": f"MY_CONSTANT = {num}  # 在模块顶部定义常量",
                        })

            if re.search(r"#\s*(TODO|FIXME|HACK|XXX)", stripped, re.IGNORECASE):
                issues.append({
                    "issue_type": "best_practice",
                    "severity": "low",
                    "description": "代码中存在 TODO/FIXME 标记，建议在提交前处理",
                    "line_number": i,
                    "original_code": stripped,
                    "suggested_fix": "处理 TODO 事项或创建 Issue 跟踪",
                })

        return issues

    # ----------------------------------------------------------
    # 行级检查
    # ----------------------------------------------------------

    def _analyze_line_level(self, code: str) -> List[Dict[str, Any]]:
        """行级别代码规范检查"""
        issues = []
        lines = code.splitlines()

        for i, line in enumerate(lines, 1):
            if len(line) > 120:
                issues.append({
                    "issue_type": "naming",
                    "severity": "low",
                    "description": f"第 {i} 行过长（{len(line)} 字符），建议拆分或使用变量提取",
                    "line_number": i,
                    "original_code": line[:80] + "...",
                    "suggested_fix": "使用括号换行或提取子表达式为变量",
                })

            stripped = line.strip()
            if re.match(r'print\s*\(', stripped) and not stripped.startswith("#"):
                issues.append({
                    "issue_type": "best_practice",
                    "severity": "low",
                    "description": "使用了 print() 输出，生产代码应使用 logging 模块",
                    "line_number": i,
                    "original_code": stripped,
                    "suggested_fix": "import logging\nlogger = logging.getLogger(__name__)\nlogger.info(...)",
                })

        return issues

    # ----------------------------------------------------------
    # 辅助方法
    # ----------------------------------------------------------

    @staticmethod
    def _count_lines(node: ast.AST) -> int:
        """计算 AST 节点占据的行数"""
        if hasattr(node, "end_lineno") and node.end_lineno:
            return node.end_lineno - node.lineno + 1
        return 0
