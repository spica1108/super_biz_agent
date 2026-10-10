"""请求数据模型

定义 API 请求的 Pydantic 模型
"""

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求"""

    id: str = Field(..., description="会话 ID", alias="Id")
    question: str = Field(..., description="用户问题", alias="Question")

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "Id": "session-123",
                "Question": "什么是向量数据库？"
            }
        }


class ClearRequest(BaseModel):
    """清空会话请求"""

    session_id: str = Field(..., description="会话 ID", alias="sessionId")

    class Config:
        populate_by_name = True


class MultimodalEmbeddingRequest(BaseModel):
    """多模态 embedding 请求"""

    input: list[dict[str, Any]] = Field(..., description="Ark 多模态 input 数组")
    model: str | None = Field(None, description="模型名称，不传则使用配置")
    encoding_format: str = Field("float", description="向量编码格式")

    class Config:
        json_schema_extra = {
            "example": {
                "model": "doubao-embedding-vision-250615",
                "encoding_format": "float",
                "input": [
                    {
                        "type": "video_url",
                        "video_url": {
                            "url": "https://ark-project.tos-cn-beijing.volces.com/doc_video/ark_vlm_video_input.mp4"
                        },
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/tower.png"
                        },
                    },
                    {
                        "type": "text",
                        "text": "视频和图片里有什么",
                    },
                ],
            }
        }
