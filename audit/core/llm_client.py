"""
LLM 客户端模块

支持通过 Anthropic 兼容接口调用小米 MiMo 大模型，
同时支持 OpenAI 兼容接口的其他模型（DeepSeek、GPT-4o 等）。

使用方式：
    from audit.core.llm_client import LLMClient

    client = LLMClient()
    response = client.chat("请分析这段代码的安全问题", code="...")
"""

import json
import logging
from typing import Dict, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# 各 provider 的默认配置
PROVIDER_DEFAULTS = {
    "mimo": {
        "base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
        "model": "mimo-v2.5-pro",
        "name": "小米 MiMo",
        "api_type": "anthropic",  # 使用 Anthropic SDK
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "name": "DeepSeek V3",
        "api_type": "openai",  # 使用 OpenAI 兼容接口
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "name": "GPT-4o",
        "api_type": "openai",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "name": "通义千问 Plus",
        "api_type": "openai",
    },
}


class LLMClient:
    """
    LLM 统一客户端

    根据 provider 自动选择调用方式：
    - mimo：使用 Anthropic SDK（anthropic 包）
    - 其他：使用 httpx 调用 OpenAI 兼容接口
    """

    def __init__(
        self,
        provider: str = None,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
    ):
        # 从 settings 读取配置
        llm_config = getattr(settings, "LLM_CONFIG", {})

        self.provider = provider or llm_config.get("provider", "mimo")
        provider_cfg = PROVIDER_DEFAULTS.get(self.provider, PROVIDER_DEFAULTS["mimo"])

        self.api_key = api_key or llm_config.get("api_key", "")
        self.base_url = (base_url or llm_config.get("base_url", "")).rstrip("/")
        self.model = model or llm_config.get("model", "")
        self.api_type = provider_cfg["api_type"]

        # 填充默认值
        if not self.base_url:
            self.base_url = provider_cfg["base_url"]
        if not self.model:
            self.model = provider_cfg["model"]

        self.provider_name = provider_cfg["name"]

        if not self.api_key:
            logger.warning(
                f"未配置 LLM API Key，LLM 功能将降级为规则引擎。"
                f"请在 settings.py 的 LLM_CONFIG 中设置 api_key"
            )

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Optional[str]:
        """
        调用 LLM 进行对话

        根据 api_type 自动选择 Anthropic SDK 或 OpenAI 兼容接口。

        Args:
            system_prompt : 系统提示词
            user_message  : 用户消息
            temperature   : 温度参数
            max_tokens    : 最大输出 token 数

        Returns:
            LLM 的响应文本，失败时返回 None
        """
        if not self.api_key:
            logger.warning("API Key 未配置，跳过 LLM 调用")
            return None

        if self.api_type == "anthropic":
            return self._chat_anthropic(system_prompt, user_message, temperature, max_tokens)
        else:
            return self._chat_openai(system_prompt, user_message, temperature, max_tokens)

    def _chat_anthropic(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float,
        max_tokens: int,
    ) -> Optional[str]:
        """通过 Anthropic SDK 调用（小米 MiMo），带重试"""
        import time

        for attempt in range(3):
            try:
                import anthropic

                client = anthropic.Anthropic(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=180.0,  # 3 分钟超时
                )

                logger.info(f"调用 {self.provider_name} ({self.model}) [Anthropic SDK] 尝试 {attempt+1}/3 ...")

                message = client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": user_message},
                    ],
                )

                content = ""
                for block in message.content:
                    if hasattr(block, "text"):
                        content += block.text

                logger.info(f"{self.provider_name} 响应成功，输出 {len(content)} 字符")
                return content

            except ImportError:
                logger.error("anthropic 包未安装，请执行: pip install anthropic")
                return None
            except Exception as e:
                logger.warning(f"第 {attempt+1} 次调用失败: {e}")
                if attempt < 2:
                    time.sleep(2)  # 等 2 秒后重试
                else:
                    logger.error(f"LLM 调用 3 次均失败，降级为规则引擎")
                    return None

    def _chat_openai(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float,
        max_tokens: int,
    ) -> Optional[str]:
        """通过 OpenAI 兼容接口调用（DeepSeek / GPT-4o / Qwen）"""
        try:
            import httpx

            url = f"{self.base_url}/chat/completions"

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            logger.info(f"调用 {self.provider_name} ({self.model}) [OpenAI 兼容] ...")

            with httpx.Client(timeout=120) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            logger.info(f"{self.provider_name} 响应成功，输出 {len(content)} 字符")
            return content

        except ImportError:
            logger.error("httpx 未安装，请执行: pip install httpx")
            return None
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}", exc_info=True)
            return None

    def analyze_code(self, code: str, context: Dict = None) -> Optional[List[Dict]]:
        """
        使用 LLM 分析代码质量，返回结构化的问题列表

        Args:
            code    : 待分析的代码
            context : 可选上下文（file_path, language 等）

        Returns:
            问题列表，每个元素是 dict。LLM 不可用时返回 None。
        """
        context = context or {}
        language = context.get("language", "Python")

        system_prompt = """你是一位资深的代码审计专家和重构顾问。你的任务是分析用户提交的代码，找出代码质量问题并给出重构建议。

请严格按照以下 JSON 格式返回结果，不要包含任何其他文字：

[
  {
    "issue_type": "问题类型",
    "severity": "严重程度",
    "description": "问题的详细描述",
    "line_number": 行号,
    "original_code": "有问题的原始代码片段",
    "suggested_fix": "修复后的代码或修复建议"
  }
]

issue_type 可选值：complexity / naming / best_practice / security / performance
severity 可选值：low / medium / high / critical

分析维度：
1. 代码复杂度（函数过长、嵌套过深、参数过多）
2. 命名规范（变量名/函数名是否清晰、魔法数字）
3. 最佳实践（异常处理、资源管理、日志使用）
4. 性能问题（不必要的循环、重复计算）
5. 安全隐患

只返回 JSON 数组，不要有其他内容。如果没有发现问题，返回空数组 []。"""

        user_message = f"请分析以下 {language} 代码：\n\n```{language.lower()}\n{code}\n```"

        response = self.chat(system_prompt, user_message)
        if not response:
            return None

        return self._parse_json_response(response)

    @staticmethod
    def _parse_json_response(response: str) -> Optional[List[Dict]]:
        """解析 LLM 返回的 JSON 响应"""
        text = response.strip()

        # 移除 markdown 代码块标记
        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1:]
            if text.endswith("```"):
                text = text[:-3].strip()

        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
            logger.warning(f"LLM 返回了非数组格式: {type(result)}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"LLM 返回的 JSON 解析失败: {e}\n原始响应: {response[:500]}")
            return None
