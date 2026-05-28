"""
Multi-Agent 调度器（Orchestrator）

职责：协调多个专职 Agent 的执行流程，汇总分析结果。

调度策略：
┌─────────────────────────────────────────────────────────────────┐
│                        Orchestrator                              │
│                                                                  │
│   输入代码 ──→ 并行分发给三个 Agent ──→ 收集 AgentResult ──→ 合并输出 │
│                                                                  │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐      │
│   │ SecurityAgent │  │ RefactorAgent │  │ SimilarityAgent  │      │
│   │  (安全扫描)    │  │  (代码质量)    │  │  (相似度检索)    │      │
│   └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘      │
│          │                 │                    │                 │
│          └─────────────────┼────────────────────┘                │
│                            ▼                                     │
│                    汇总为 PipelineResult                          │
│                    （去重 + 严重程度排序 + 写入数据库）                │
└─────────────────────────────────────────────────────────────────┘
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .agents.base import BaseAgent, AgentResult
from .agents.security_agent import SecurityAgent
from .agents.refactor_agent import RefactorAgent
from .agents.similarity_agent import SimilarityAgent

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """
    整条流水线的汇总结果

    Attributes:
        agent_results : 各 Agent 的独立执行结果
        all_issues    : 合并去重后的全部问题列表（按严重程度排序）
        total_issues  : 问题总数
        total_duration: 流水线总耗时（秒）
        summary       : 一句话执行摘要
    """
    agent_results: List[AgentResult] = field(default_factory=list)
    all_issues: List[Dict[str, Any]] = field(default_factory=list)
    total_issues: int = 0
    total_duration: float = 0.0
    summary: str = ""


# 严重程度权重，用于排序
_SEVERITY_WEIGHT = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


class Orchestrator:
    """
    Multi-Agent 调度器

    使用方法：
        orchestrator = Orchestrator()
        result = orchestrator.run_pipeline(code="...", context={"file_path": "app.py"})
    """

    def __init__(self):
        # 初始化三个专职 Agent
        self.agents: List[BaseAgent] = [
            SecurityAgent(),
            RefactorAgent(),
            SimilarityAgent(),
        ]

    def run_pipeline(
        self,
        code: str,
        context: Dict[str, Any] = None,
    ) -> PipelineResult:
        """
        执行完整的代码审计流水线

        流程：
        ① 依次调用每个 Agent（顺序执行，避免并发引入的复杂性）
        ② 收集所有 AgentResult
        ③ 合并、去重、排序问题列表
        ④ 返回 PipelineResult

        Args:
            code    : 待审计的完整代码字符串
            context : 可选上下文信息，会透传给每个 Agent
                      支持的 key：
                      - file_path : 文件路径
                      - language  : 编程语言
                      - top_k     : 相似度检索返回数量

        Returns:
            PipelineResult 对象
        """
        context = context or {}
        agent_results: List[AgentResult] = []

        logger.info("=" * 60)
        logger.info("Orchestrator 启动审计流水线")
        logger.info("=" * 60)

        # ----------------------------------------------------------
        # 步骤 1：依次执行每个 Agent
        # ----------------------------------------------------------
        for agent in self.agents:
            logger.info(f"→ 正在执行 {agent.name} ...")
            result = agent.run(code, context)
            agent_results.append(result)

            if not result.success:
                logger.warning(f"  {agent.name} 执行失败: {result.summary}")
            else:
                logger.info(f"  {agent.name} 完成: {result.summary}")

        # ----------------------------------------------------------
        # 步骤 2：合并所有 issues
        # ----------------------------------------------------------
        all_issues = []
        for result in agent_results:
            all_issues.extend(result.issues)

        # ----------------------------------------------------------
        # 步骤 3：去重（基于 issue_type + line_number）
        # ----------------------------------------------------------
        seen = set()
        unique_issues = []
        for issue in all_issues:
            key = (issue.get("issue_type", ""), issue.get("line_number", 0))
            if key not in seen:
                seen.add(key)
                unique_issues.append(issue)

        # ----------------------------------------------------------
        # 步骤 4：按严重程度排序
        # ----------------------------------------------------------
        unique_issues.sort(
            key=lambda x: _SEVERITY_WEIGHT.get(x.get("severity", "info"), 99)
        )

        # ----------------------------------------------------------
        # 步骤 5：计算总耗时
        # ----------------------------------------------------------
        total_duration = sum(r.duration_sec for r in agent_results)

        summary = (
            f"审计流水线完成 | "
            f"Agent 数: {len(agent_results)} | "
            f"发现问题: {len(unique_issues)} | "
            f"总耗时: {total_duration:.3f}s"
        )

        logger.info("=" * 60)
        logger.info(summary)
        logger.info("=" * 60)

        return PipelineResult(
            agent_results=agent_results,
            all_issues=unique_issues,
            total_issues=len(unique_issues),
            total_duration=round(total_duration, 3),
            summary=summary,
        )

    def to_api_response(self, pipeline_result: PipelineResult) -> Dict[str, Any]:
        """
        将 PipelineResult 转换为可直接返回给前端的字典格式

        Args:
            pipeline_result : run_pipeline() 的返回值

        Returns:
            可被 DRF Response 序列化的字典
        """
        return {
            "summary": pipeline_result.summary,
            "total_issues": pipeline_result.total_issues,
            "total_duration_sec": pipeline_result.total_duration,
            "agent_details": [
                {
                    "agent_name": r.agent_name,
                    "success": r.success,
                    "summary": r.summary,
                    "issues_count": len(r.issues),
                    "duration_sec": r.duration_sec,
                }
                for r in pipeline_result.agent_results
            ],
            "issues": pipeline_result.all_issues,
        }
