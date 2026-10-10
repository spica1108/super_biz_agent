"""Embedding 接口模块"""

from fastapi import APIRouter
from loguru import logger

from app.models.request import MultimodalEmbeddingRequest
from app.services.vector_embedding_service import vector_embedding_service

router = APIRouter()


@router.post("/embeddings/multimodal")
async def create_multimodal_embedding(request: MultimodalEmbeddingRequest):
    """创建多模态 embedding。"""
    try:
        result = vector_embedding_service.embed_multimodal(
            inputs=request.input,
            model=request.model,
            encoding_format=request.encoding_format,
        )
        return {
            "code": 200,
            "message": "success",
            "data": result,
        }
    except Exception as e:
        logger.error(f"多模态 embedding 创建失败: {e}")
        return {
            "code": 500,
            "message": "error",
            "data": {
                "success": False,
                "errorMessage": str(e),
            },
        }
