"""对话接口

提供基于 RAG Agent 的普通对话和流式对话接口
本文件只负责接收 HTTP 请求、包装响应，并把业务处理转交给 rag_agent_service
"""

import json
from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse
from app.models.request import ChatRequest, ClearRequest
from app.models.response import SessionInfoResponse, ApiResponse
from app.agent.mcp_client import format_exception_chain
from app.services.rag_agent_service import rag_agent_service
from loguru import logger

router = APIRouter()


# 普通聊天接口：适合“一问一答、一次性拿完整结果”的场景。
# 真实的 RAG/Agent 处理逻辑不在 API 层，而是交给 rag_agent_service.query。
@router.post("/chat")
async def chat(request: ChatRequest):
    """快速对话接口
    {
        "code": 200,
        "message": "success",
        "data": {
            "success": true,
            "answer": "回答内容",
            "errorMessage": null
        }
    }

    Args:
        request: 对话请求

    Returns:
        统一格式的对话响应
    """
    try:
        # request.id 是会话 ID，后续会作为 Agent 的 session/thread 标识。
        # request.question 是用户本次输入的问题。
        logger.info(f"[会话 {request.id}] 收到快速对话请求: {request.question}")
        answer = await rag_agent_service.query(
            request.question,
            session_id=request.id
        )

        logger.info(f"[会话 {request.id}] 快速对话完成")

        return {
            "code": 200,
            "message": "success",
            "data": {
                "success": True,
                "answer": answer,
                "errorMessage": None
            }
        }

    except Exception as e:
        # 这里选择返回统一 JSON，而不是抛 HTTPException。
        # 注意：HTTP 状态码可能仍是 200，业务是否成功由 body.code/data.success 判断。
        logger.error(f"对话接口错误: {e}")
        return {
            "code": 500,
            "message": str(e),
            "data": {
                "success": False,
                "answer": None,
                "errorMessage": str(e)
            }
        }


# 流式聊天接口：适合前端边生成边展示答案。
# 将 Service 层产出的内部 chunk 转换为符合 SSE 规范的格式
# 返回格式是 SSE（Server-Sent Events），前端可以持续接收 message 事件。
@router.post("/chat_stream")
async def chat_stream(request: ChatRequest):
    """流式对话接口（基于 RAG Agent，SSE）

    返回 SSE 格式，data 字段为 JSON：

    工具调用事件:
    event: message
    data: {"type":"tool_call","data":{"tool":"工具名","status":"start|end","input":{...}}}

    内容流式事件:
    event: message
    data: {"type":"content","data":"内容块"}

    完成事件:
    event: message
    data: {"type":"done","data":{"answer":"完整答案","tool_calls":[...]}}

    Args:
        request: 对话请求

    Returns:
        SSE 事件流
    """
    logger.info(f"[会话 {request.id}] 收到流式对话请求: {request.question}")

    # EventSourceResponse 需要一个生成器不断 yield 事件。
    # 这里的 event_generator 负责把 service 层产出的 chunk 转成前端可消费的 SSE 消息。
    async def event_generator():
        try:
            # query_stream 是真正的流式 Agent 调用入口。
            # 它会逐步产出 content/tool_call/search_results 等不同类型的 chunk。
            async for chunk in rag_agent_service.query_stream(request.question, session_id=request.id):
                chunk_type = chunk.get("type", "unknown")
                chunk_data = chunk.get("data", None)

                # 处理调试类型消息（新增）
                if chunk_type == "debug":
                    # 调试信息，可以选择发送或忽略
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "debug",
                            # debug 事件保留节点名和消息类型，方便排查 LangGraph/Agent 流程。
                            "node": chunk.get("node", "unknown"),
                            "message_type": chunk.get("message_type", "unknown")
                        }, ensure_ascii=False)
                    }
                elif chunk_type == "tool_call":
                    # 发送工具调用事件（可选，前端可以显示工具调用状态）
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "tool_call",
                            "data": chunk_data
                        }, ensure_ascii=False)
                    }
                elif chunk_type == "search_results":
                    # 发送检索结果（可选，前端可以忽略，也可以用来展示“引用来源”）
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "search_results",
                            "data": chunk_data
                        }, ensure_ascii=False)
                    }
                elif chunk_type == "content":
                    # 发送答案内容块。
                    # 关键：SSE 的 data 字段必须是字符串，所以这里用 json.dumps 包一层。
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "content",
                            "data": chunk_data
                        }, ensure_ascii=False)
                    }
                elif chunk_type == "complete":
                    # 发送完成信号。
                    # service 层叫 complete，这里对前端输出成 done。
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "done",
                            "data": chunk_data
                        }, ensure_ascii=False)
                    }
                elif chunk_type == "error":
                    # 发送错误信息
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "error",
                            "data": str(chunk_data)
                        }, ensure_ascii=False)
                    }

            logger.info(f"[会话 {request.id}] 流式对话完成")

        except Exception as e:
            # 流式接口已经开始返回数据后，不能再像普通接口那样直接抛 HTTPException。
            # 因此这里把异常包装成一条 error 事件发给前端。
            logger.error(f"流式对话接口错误: {format_exception_chain(e)}")
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "error",
                    "data": str(e)
                }, ensure_ascii=False)
            }

    # EventSourceResponse 会保持连接打开，直到 event_generator 结束。
    return EventSourceResponse(event_generator())


# 清空指定会话的历史记录。
# 会话数据由 rag_agent_service 内部的 LangGraph checkpointer/session 逻辑维护。
@router.post("/chat/clear", response_model=ApiResponse)
async def clear_session(request: ClearRequest):
    """清空会话历史

    Args:
        request: 清空请求

    Returns:
        操作结果
    """
    try:
        # request.session_id 指定要清理哪一个会话。
        success = rag_agent_service.clear_session(request.session_id)
        logger.info(f"清空会话: {request.session_id}, 结果: {success}")

        return ApiResponse(
            status="success" if success else "error",
            message="会话已清空" if success else "清空会话失败",
            data=None
        )

    except Exception as e:
        # 管理类接口这里使用 FastAPI 标准异常，让客户端收到 500 状态码。
        logger.error(f"清空会话错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 查询指定会话的历史消息，用于调试或前端恢复会话状态。
@router.get("/chat/session/{session_id}", response_model=SessionInfoResponse)
async def get_session_info(session_id: str) -> SessionInfoResponse:
    """查询会话历史

    Args:
        session_id: 会话 ID

    Returns:
        会话信息
    """
    try:
        # 根据 session_id 从 RAG Agent 服务中取出历史消息。
        history = rag_agent_service.get_session_history(session_id)

        return SessionInfoResponse(
            session_id=session_id,
            message_count=len(history),
            history=history
        )

    except Exception as e:
        logger.error(f"获取会话信息错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))
