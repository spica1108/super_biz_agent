"""LLM 工厂类 - 统一创建 OpenAI 兼容聊天模型。"""

from langchain_openai import ChatOpenAI
from app.config import config
from loguru import logger


class LLMFactory:
    """LLM 工厂类 - 使用 OpenAI 兼容模式"""

    DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    VOLCENGINE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

    @staticmethod
    def _provider_base_url(provider: str) -> str:
        if provider == "volcengine":
            return LLMFactory.VOLCENGINE_BASE_URL
        return LLMFactory.DASHSCOPE_BASE_URL

    @staticmethod
    def _default_model(provider: str) -> str:
        if provider == "volcengine":
            return config.llm_model or config.rag_model
        return config.llm_model or config.dashscope_model

    @staticmethod
    def _default_api_key(provider: str) -> str:
        return config.llm_api_key or config.dashscope_api_key

    @staticmethod
    def create_chat_model(
        model: str | None = None,
        temperature: float = 0.7,
        streaming: bool = True,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> ChatOpenAI:
        provider = config.llm_provider.lower()
        model = model or LLMFactory._default_model(provider)
        base_url = base_url or config.llm_base_url or LLMFactory._provider_base_url(provider)
        api_key = api_key or LLMFactory._default_api_key(provider)

        masked_key = f"{api_key[:8]}...{api_key[-4:]}" if api_key and len(api_key) > 12 else "***"
        logger.info(
            f"创建聊天模型: provider={provider}, model={model}, "
            f"base_url={base_url}, api_key={masked_key}, streaming={streaming}"
        )

        # DeepSeek 平台的模型默认开启 thinking 模式，thinking 下不支持强制 tool_choice，
        # 结构化输出（with_structured_output(method="function_calling")）会 400。
        # 仅对 DeepSeek 端点关闭 thinking，不影响其它 provider。
        extra_kwargs: dict = {}
        if base_url and "deepseek" in base_url.lower():
            extra_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            base_url=base_url,
            api_key=api_key,
            **extra_kwargs,
        )

        return llm

# 全局 LLM 工厂实例
llm_factory = LLMFactory()
