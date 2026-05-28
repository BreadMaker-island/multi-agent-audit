"""
相似度检索 Agent

职责：封装 search_similar_cases() 函数，将其集成到 Multi-Agent 流水线中。
与独立调用 search_similar_cases() 的区别在于：
- 返回标准的 AgentResult 对象
- 支持从数据库动态加载历史案例
- 可被 Orchestrator 统一调度
"""

import logging
from typing import Any, Dict

from .base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)


class SimilarityAgent(BaseAgent):
    """
    相似度检索 Agent

    工作流程：
    ① 调用 search_similar_cases() 检索相似历史案例
    ② 将结果封装为标准 AgentResult
    """

    def __init__(self):
        super().__init__(name="SimilarityAgent")

    def execute(self, code: str, context: Dict[str, Any]) -> AgentResult:
        """
        执行相似度检索

        Args:
            code    : 待检索的代码片段
            context : 可选上下文，支持 'top_k' 键（默认为 3）

        Returns:
            AgentResult，details 中包含 'similar_cases' 列表
        """
        from ..similarity import search_similar_cases

        top_k = context.get("top_k", 3)

        # 调用核心检索函数
        similar_cases = search_similar_cases(code, top_k=top_k)

        # 将检索结果转换为 issues 格式（每个相似案例视为一个「参考项」）
        issues = []
        for case in similar_cases:
            issues.append({
                "issue_type": f"相似案例: {case['issue_type']}",
                "severity": "info",
                "description": case["description"],
                "line_number": 0,
                "original_code": case["original_code"],
                "suggested_fix": case["suggested_fix"],
                "similarity_score": case["similarity"],
            })

        best_score = similar_cases[0]["similarity"] if similar_cases else 0.0
        summary = (
            f"检索到 {len(similar_cases)} 个相似历史案例，"
            f"最高相似度 {best_score:.2%}"
        )

        return AgentResult(
            agent_name=self.name,
            success=True,
            issues=issues,
            summary=summary,
            details={
                "similar_cases": similar_cases,
                "best_similarity_score": best_score,
            },
        )
