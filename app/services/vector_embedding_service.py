"""向量嵌入服务模块 - 基于 LangChain Embeddings 标准接口"""

from typing import Any, List

from langchain_core.embeddings import Embeddings
import httpx
from openai import OpenAI
from loguru import logger

from app.config import config


class DashScopeEmbeddings(Embeddings):
    """OpenAI 兼容 Embeddings 服务
    
    实现 LangChain 标准 Embeddings 接口:
    - embed_documents(texts: List[str]) → List[List[float]]: 批量嵌入文档
    - embed_query(text: str) → List[float]: 嵌入单个查询
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-v4",
        dimensions: int = 1024,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        endpoint_path: str = "",
    ):
        """
        初始化 OpenAI 兼容 Embeddings
        
        Args:
            api_key: DashScope API Key
            model: 嵌入模型名称
            dimensions: 向量维度
        """
        self.api_key = api_key
        self.client: OpenAI | None = None
        self.model = model
        self.dimensions = dimensions
        self.base_url = base_url
        self.endpoint_path = endpoint_path

        if self._is_placeholder_key(api_key):
            logger.warning("Embedding API Key 未配置，Embedding 服务将在调用时不可用")
        else:
            self._ensure_client()

    @staticmethod
    def _mask_api_key(api_key: str) -> str:
        """掩码 API Key 用于日志"""
        if len(api_key) > 8:
            return f"{api_key[:8]}...{api_key[-4:]}"
        return "***"

    @staticmethod
    def _is_placeholder_key(api_key: str) -> bool:
        return not api_key or api_key in {
            "your-api-key-here",
            "your-volcengine-api-key-here",
        }

    def _ensure_client(self) -> OpenAI:
        """按需创建 OpenAI 兼容客户端，避免缺少 API Key 时阻塞应用启动。"""
        if self.client is not None:
            return self.client

        if self._is_placeholder_key(self.api_key):
            raise ValueError("请设置 EMBEDDING_API_KEY 或 LLM_API_KEY")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

        masked_key = self._mask_api_key(self.api_key)
        logger.info(
            f"Embeddings 初始化完成 - "
            f"模型: {self.model}, 维度: {self.dimensions}, "
            f"base_url: {self.base_url}, API Key: {masked_key}"
        )
        return self.client

    @property
    def _use_multimodal_endpoint(self) -> bool:
        return self.endpoint_path.rstrip("/") == "/embeddings/multimodal"

    def _multimodal_url(self) -> str:
        endpoint_path = self.endpoint_path or "/embeddings/multimodal"
        return f"{self.base_url.rstrip('/')}{endpoint_path}"

    def _post_multimodal_embedding(self, payload: dict[str, Any]) -> dict[str, Any]:
        """调用火山方舟多模态 embedding 接口。"""
        if self._is_placeholder_key(self.api_key):
            raise ValueError("请设置 EMBEDDING_API_KEY 或 LLM_API_KEY")

        response = httpx.post(
            self._multimodal_url(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_embedding(data: dict[str, Any]) -> List[float]:
        embedding = data.get("data", {}).get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError(f"Embedding 响应格式异常: {data}")
        return embedding

    def _embed_text_multimodal(self, text: str) -> List[float]:
        """调用火山方舟多模态 embedding 接口嵌入单段文本。"""
        payload = {
            "model": self.model,
            "encoding_format": "float",
            "input": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
        }
        data = self._post_multimodal_embedding(payload)
        return self._extract_embedding(data)

    def embed_multimodal(
        self,
        inputs: list[dict[str, Any]],
        model: str | None = None,
        encoding_format: str = "float",
    ) -> dict[str, Any]:
        """嵌入文本、图片 URL、视频 URL 等多模态输入。"""
        if not inputs:
            raise ValueError("多模态 embedding input 不能为空")

        payload = {
            "model": model or self.model,
            "encoding_format": encoding_format,
            "input": inputs,
        }
        data = self._post_multimodal_embedding(payload)
        embedding = self._extract_embedding(data)

        return {
            "embedding": embedding,
            "dimension": len(embedding),
            "id": data.get("id"),
            "model": data.get("model"),
            "usage": data.get("usage"),
            "object": data.get("object"),
        }

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        向量化文档，批量嵌入文档列表 (LangChain 标准接口)
        
        Args:
            texts: 文本列表
            
        Returns:
            List[List[float]]: 嵌入向量列表
        """
        if not texts:
            return []
        
        try:
            logger.info(f"批量嵌入 {len(texts)} 个文档")
            if self._use_multimodal_endpoint:
                embeddings = [self._embed_text_multimodal(text) for text in texts]
                logger.debug(f"批量嵌入完成, 维度: {len(embeddings[0])}")
                return embeddings

            client = self._ensure_client()
            
            # 批量调用 API
            response = client.embeddings.create(
                model=self.model,
                input=texts,
                dimensions=self.dimensions,
                encoding_format="float"
            )
            
            embeddings = [item.embedding for item in response.data]
            logger.debug(f"批量嵌入完成, 维度: {len(embeddings[0])}")
            
            return embeddings
            
        except Exception as e:
            logger.error(f"批量嵌入失败: {e}")
            raise RuntimeError(f"批量嵌入失败: {e}") from e

    def embed_query(self, text: str) -> List[float]:
        """
        向量化用户问题，嵌入单个查询文本 (LangChain 标准接口)
        
        Args:
            text: 查询文本
            
        Returns:
            List[float]: 嵌入向量
        """
        if not text or not text.strip():
            raise ValueError("查询文本不能为空")
        
        try:
            logger.debug(f"嵌入查询, 长度: {len(text)} 字符")
            if self._use_multimodal_endpoint:
                embedding = self._embed_text_multimodal(text)
                logger.debug(f"查询嵌入完成, 维度: {len(embedding)}")
                return embedding

            client = self._ensure_client()
            
            response = client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions,
                encoding_format="float"
            )
            
            embedding = response.data[0].embedding
            logger.debug(f"查询嵌入完成, 维度: {len(embedding)}")
            
            return embedding
            
        except Exception as e:
            logger.error(f"查询嵌入失败: {e}")
            raise RuntimeError(f"查询嵌入失败: {e}") from e


# 全局单例
embedding_provider = config.llm_provider.lower()
default_embedding_base_url = (
    "https://ark.cn-beijing.volces.com/api/v3"
    if embedding_provider == "volcengine"
    else "https://dashscope.aliyuncs.com/compatible-mode/v1"
)

vector_embedding_service = DashScopeEmbeddings(
    api_key=config.embedding_api_key or config.llm_api_key or config.dashscope_api_key,
    model=config.embedding_model or config.dashscope_embedding_model,
    dimensions=1024,
    base_url=config.embedding_base_url or config.llm_base_url or default_embedding_base_url,
    endpoint_path=config.embedding_endpoint_path,
)
