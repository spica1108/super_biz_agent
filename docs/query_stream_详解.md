# query_stream() 详解

> 文件：[app/services/rag_agent_service.py](../app/services/rag_agent_service.py) — line 246-315

## 整体数据流

```
用户输入 "今天天气怎么样"
        │
        ▼
┌─────────────────────────────────────────────┐
│  query_stream(question="今天天气怎么样")     │
│                                             │
│  ① 准备输入 → agent.astream()               │
│  ② async for 拿到 (token, metadata)         │
│  ③ 从 token 里抽出 text → yield 出去         │
│  ④ yield {"type": "complete"} 收尾          │
└─────────────────────────────────────────────┘
        │  yield chunk1  yield chunk2  yield complete
        ▼
   API 层 (chat.py) 逐个消费
```

---

## 第一段：准备阶段（line 268-283）

```python
messages = [
    SystemMessage(content=self.system_prompt),  # "你是一个专业的AI助手..."
    HumanMessage(content=question)              # "今天天气怎么样"
]
agent_input = {"messages": messages}

config_dict = {"configurable": {"thread_id": session_id}}
```

做的事情非常简单：把系统提示 + 用户问题打包成 LangGraph 要求的格式。`thread_id` 是会话 ID，LangGraph 用它来记住历史对话。

---

## 第二段：astream() — 最关键的部分（line 285-289）

```python
async for token, metadata in self.agent.astream(
    input=agent_input,
    config=config_dict,
    stream_mode="messages",
):
```

这行代码是整个流式的核心。把它拆成两层理解：

### 第一层：`self.agent` 是什么？

回顾 `__init__`（line 138-142）：

```python
self.agent = create_agent(
    self.model,           # ChatOpenAI(streaming=True)
    tools=all_tools,      # 本地工具 + MCP 工具
    checkpointer=self.checkpointer,  # MemorySaver
)
```

`create_agent()` 是 LangChain 封装好的函数，内部会自动建一个 LangGraph 图，流程大致是：

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  用户输入  │ ──▶ │  Agent   │ ──▶ │  工具调用  │ ──▶ 循环直到 LLM 生成最终回复
└──────────┘     │  (LLM)   │     │  (tools) │
                 └──────────┘     └──────────┘
```

### 第二层：`astream(stream_mode="messages")` 在做什么？

LangGraph 提供多种流模式。`stream_mode="messages"` 的效果：

```
stream_mode="messages"
──────────────────────────────────────────────►
 LLM思考 → "今天" → "天气" → "不错" → tool_call → 工具结果 → "根据" → "查询" → ...
  ↑         ↑        ↑        ↑        ↑          ↑         ↑        ↑
  yield     yield    yield    yield    yield      yield     yield    yield
  每个 token 或消息都立刻产出，不等整个回复完成
```

```python
async for token, metadata in self.agent.astream(...):
```

每次循环拿到两个东西：

| 变量 | 类型 | 内容示例 |
|------|------|---------|
| `token` | `AIMessageChunk` 或 `AIMessage` 或 `ToolMessage` | 一个 token 片段（如 `"今天"`）或一条完整消息 |
| `metadata` | `dict` | `{"langgraph_node": "agent", "thread_id": "xxx", ...}` |

> 关键：因为 `llm_factory` 里设了 `streaming=True`，所以 LLM 不是一次性输出完整答案，而是一个 token 一个 token 往外蹦。LangGraph 每拿到一个 token 就 yield 一次。

---

## 第三段：从 token 里提取文字（line 290-306）

```python
node_name = metadata.get('langgraph_node', 'unknown')  # 是哪个 LangGraph 节点产生的
message_type = type(token).__name__                     # 消息类型: "AIMessageChunk"
```

然后核心提取逻辑：

```python
if message_type in ("AIMessage", "AIMessageChunk"):
    content_blocks = getattr(token, 'content_blocks', None)

    if content_blocks and isinstance(content_blocks, list):
        for block in content_blocks:
            if isinstance(block, dict) and block.get('type') == 'text':
                text_content = block.get('text', '')
                if text_content:
                    yield {"type": "content", "data": text_content, "node": node_name}
```

### 逐层解释

#### `token.content_blocks` 长什么样？

LangChain 新版的消息内容不是简单字符串，而是 `content_blocks` 数组。一个 `AIMessageChunk` 的 content_blocks 大概长这样：

```python
[
    {"type": "text", "text": "今天"},        # ← 我们只取这种
    # 如果是多模态，可能有:
    # {"type": "image_url", "image_url": {...}},
    # {"type": "tool_use", "id": "...", "name": "..."},
]
```

#### 为什么要循环遍历 blocks？

因为一条消息可能同时包含文字 + 工具调用 + 图片等。这里只关心 `type == "text"` 的 block，从里面取 `text` 字段。

#### yield 出去的是什么？

```python
yield {"type": "content", "data": "今天", "node": "agent"}
yield {"type": "content", "data": "天气", "node": "agent"}
yield {"type": "content", "data": "不错", "node": "agent"}
```

这是一条 Python 异步生成器（`AsyncGenerator`），调用方（`chat.py`）用 `async for chunk in query_stream()` 逐个接收。

---

## 第四段：收尾（line 308-315）

```python
logger.info("流式完成")
yield {"type": "complete"}   # ← 告诉上层"我结束了"
```

LLM 所有 token 吐完之后，yield 一个特殊的 complete 信号。上层 API 收到后会把流关掉。

异常时 yield `{"type": "error"}` 保证前端不会 hang 住。

---

## 完整时序图

```
时间 ───────────────────────────────────────────────────►

LLM (API)
  │ token: "今天"    token: "天气"    token: "不错"      [结束]
  │       │               │               │               │
  ▼       ▼               ▼               ▼               ▼
LangGraph astream()
  │ yield (AIMessageChunk("今天"),   metadata)
  │ yield (AIMessageChunk("天气"),   metadata)
  │ yield (AIMessageChunk("不错"),   metadata)
  │       │               │               │
  ▼       ▼               ▼               ▼
query_stream() 的 for 循环
  │ content_blocks → type=="text" → text="今天"  → yield {"type":"content", "data":"今天"}
  │ content_blocks → type=="text" → text="天气"  → yield {"type":"content", "data":"天气"}
  │ content_blocks → type=="text" → text="不错"  → yield {"type":"content", "data":"不错"}
  │                                                      │
  │                                              yield {"type":"complete"}
  ▼       ▼               ▼               ▼               ▼
API 层 chat.py
  │ 转成 SSE: {"event":"message", "data":'{"type":"content","data":"今天"}'}
  │ 转成 SSE: {"event":"message", "data":'{"type":"content","data":"天气"}'}
  │ ...
  │ 转成 SSE: {"event":"message", "data":'{"type":"done"}'}

  ▼       ▼               ▼               ▼               ▼
前端 app.js
  │ ReadableStream → 逐行解析 → innerHTML 实时渲染
  │ "今天" → "今天天气" → "今天天气不错"
```

---

## 对比：非流式 query()

```python
# query() 方法（line 217-220）
result = await self.agent.ainvoke(input=agent_input, config=config_dict)
#                   ↑ ainvoke = 等全部完成再返回
last_message = result["messages"][-1]
return last_message.content
```

| 维度 | `ainvoke()` (query) | `astream()` (query_stream) |
|------|-------------------|---------------------------|
| 返回时机 | LLM 完全结束后 | 每产生一个 token 立刻返回 |
| 返回内容 | 完整答案字符串 | 逐个 chunk 字典 |
| 前端体验 | 一次显示全部 | 打字机效果逐字出现 |
| 底层调用 | `stream=False` | `stream=True` |

---

## 一句话总结

`query_stream()` 就是把 LangGraph 内部 `streaming=True` 产生的 token 碎片，从 `content_blocks` 结构里把纯文字抠出来，包装成 `{"type": "content", "data": "xxx"}` 的字典，逐个 yield 给上层。上层（API）再套一层 SSE 协议发给前端。
