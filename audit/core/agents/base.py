"""
Agent 基类模块

Multi-Agent 架构的核心抽象层。所有专职 Agent 必须继承 BaseAgent 并实现 execute() 方法。

设计模式：模板方法模式（Template Method）
- BaseAgent.run() 定义了统一的执行流程：前置检查 → 执行 → 后处理
- 子类只需实现 execute() 即可，无需关心异常捕获、耗时统计等通用逻辑
"""

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """
    Agent 执行结果的统一数据结构

    所有 Agent 返回结果都必须封装为 AgentResult，保证 Orchestrator
    可以用统一的方式处理不同 Agent 的输出。

    Attributes:
        agent_name  : 产生该结果的 Agent 名称
        success     : 执行是否成功
        issues      : 发现的问题列表，每个元素是 dict（含 issue_type, severity, description 等）
        summary     : 执行摘要（一句话概述）
        details     : 任意附加详情（由各 Agent 自定义）
        duration_sec: 执行耗时（秒）
    """
    agent_name: str
    success: bool
    issues: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    duration_sec: float = 0.0


class BaseAgent(ABC):
    """
    Agent 抽象基类

    所有专职 Agent（安全扫描、重构建议、相似度检索）都必须：
    ① 继承 BaseAgent
    ② 实现 execute(code: str, context: dict) -> AgentResult 方法

    Attributes:
        name : Agent 名称，用于日志和结果标识
    """

    def __init__(self, name: str):
        self.name = name

    def run(self, code: str, context: Dict[str, Any] = None) -> AgentResult:
        """
        模板方法：统一的执行入口

        流程：记录开始 → 调用子类 execute() → 捕获异常 → 统计耗时

        Args:
            code    : 待分析的代码字符串
            context : 可选的上下文信息（如文件路径、编程语言等）

        Returns:
            AgentResult 对象
        """
        context = context or {}
        start = time.time()

        logger.info(f"[{self.name}] 开始执行分析...")

        try:
            result = self.execute(code, context)
        except Exception as e:
            logger.error(f"[{self.name}] 执行异常: {e}", exc_info=True)
            result = AgentResult(
                agent_name=self.name,
                success=False,
                summary=f"Agent 执行失败: {e}",
            )

        result.duration_sec = round(time.time() - start, 3)
        logger.info(
            f"[{self.name}] 执行完成 | 耗时 {result.duration_sec}s | "
            f"发现 {len(result.issues)} 个问题"
        )
        return result

    @abstractmethod
    def execute(self, code: str, context: Dict[str, Any]) -> AgentResult:
        """
        子类必须实现的核心分析方法

        Args:
            code    : 待分析的代码字符串
            context : 上下文信息字典

        Returns:
            AgentResult 对象
        """
        ...
