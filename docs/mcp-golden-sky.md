# MCP 学习计划 — SuperBizAgent 项目

## Context

SuperBizAgent 是企业级 AIOps 智能运维助手（Python/FastAPI/LangChain/LangGraph）。通过 MCP 协议将 AI Agent 与日志查询（CLS）、监控数据（Monitor）工具连接。学习目标：掌握 MCP 三层架构——Server 端工具定义 → Client 端连接管理 → Agent 业务集成。

---

## 先看全景：MCP 三层架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI 主应用 (Host)                     │
│  ┌──────────────────────┐  ┌──────────────────────────────┐ │
│  │    RAG Agent (ReAct)  │  │   AIOps Agent (Plan-Exec)    │ │
│  │  rag_agent_service.py │  │  planner / executor /        │ │
│  │                       │  │  replanner                   │ │
│  └──────────┬────────────┘  └──────────────┬───────────────┘ │
│             │                              │                  │
│             └──────────────┬───────────────┘                  │
│                            ▼                                  │
│           ┌────────────────────────────────┐                 │
│           │       MCP Client (单例)         │                 │
│           │     mcp_client.py              │                 │
│           │   MultiServerMCPClient         │                 │
│           │   + retry_interceptor          │                 │
│           └────────┬───────────┬───────────┘                 │
│                    │           │                              │
└────────────────────┼───────────┼──────────────────────────────┘
                     │           │
            streamable-http  streamable-http
           localhost:8003/mcp  localhost:8004/mcp
                     │           │
     ┌───────────────▼──┐  ┌─────▼────────────────┐
     │  CLS MCP Server  │  │ Monitor MCP Server   │
     │  cls_server.py   │  │ monitor_server.py    │
     │  FastMCP("CLS")  │  │ FastMCP("Monitor")   │
     │                  │  │                      │
     │  5 个工具:        │  │  2 个工具:            │
     │  · get_current_  │  │  · query_cpu_metrics │
     │    timestamp     │  │  · query_memory_     │
     │  · get_region_   │  │    metrics           │
     │    code_by_name  │  │                      │
     │  · get_topic_    │  │                      │
     │    info_by_name  │  │                      │
     │  · search_topic_ │  │                      │
     │    by_service_name│  │                      │
     │  · search_log    │  │                      │
     └──────────────────┘  └──────────────────────┘
```

**知识点 — MCP 三大角色**：
| 角色 | 本项目中的对应 | 职责 |
|------|---------------|------|
| **Host** | FastAPI 主应用 (`app/main.py`) | 发起 AI 请求，消费工具 |
| **Client** | `mcp_client.py` → `MultiServerMCPClient` | 连接 Server，获取工具列表，路由调用 |
| **Server** | `cls_server.py` / `monitor_server.py` | 暴露具体的工具实现 |

**知识点 — Transport（传输方式）**：
- `streamable-http`：本地 FastMCP 服务使用，HTTP + 流式响应
- `sse`：腾讯云等托管 MCP 端点使用，Server-Sent Events
- `stdio`：进程间标准输入输出通信（本项目未使用）

---

## 阶段一：MCP Server 构建（60-120min）⭐⭐⭐

> 从零理解如何用 FastMCP 把 Python 函数变成 AI 可调用的工具。

### 1.1 最小可运行骨架

**[mcp_servers/cls_server.py](mcp_servers/cls_server.py)** 的核心结构：

```python
# L1-21: 导入 + 日志配置 + 创建 FastMCP 实例
from fastmcp import FastMCP                # L11
mcp = FastMCP("CLS")                       # L20 — 服务名称 "CLS"

# L23-69: 自定义日志装饰器（非必须，但强烈推荐）
def log_tool_call(func):                   # L23
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"调用方法: {func.__name__}")  # L30
        logger.info(f"参数信息:\n{json.dumps(kwargs, ...)}")  # L37
        try:
            result = func(*args, **kwargs)
            logger.info("返回状态: SUCCESS")      # L49
            return result
        except Exception as e:
            logger.error(f"错误信息: {str(e)}")   # L65
            raise
    return wrapper

# L469-470: 启动服务
if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8003, path="/mcp")
```

**知识点 — `@mcp.tool()` 装饰器原理**：
FastMCP 的 `@mcp.tool()` 读取函数的类型注解（`str`, `int`, `Optional[str]`）和文档字符串，自动生成 MCP 协议的 JSON Schema。LLM 就是通过这个 Schema 理解工具的功能和参数类型，从而决定何时调用、传什么参数。

### 1.2 工具定义的标准模式

以 `get_current_timestamp` 为例（[cls_server.py](mcp_servers/cls_server.py) L104-133）：

```python
@mcp.tool()                    # ← 注册为 MCP 工具
@log_tool_call                 # ← 日志装饰器（先执行）
def get_current_timestamp() -> int:
    """获取当前时间戳（以毫秒为单位）。       ← LLM 通过这段文字理解工具用途

    此工具用于获取标准的毫秒时间戳，可用于：
    1. 作为 search_log 的 end_time 参数
    2. 计算历史时间点作为 start_time 参数

    Returns:
        int: 当前时间戳（毫秒），例如: 1708012345000

    使用示例:
        current = get_current_timestamp()
        fifteen_min_ago = current - (15 * 60 * 1000)
    """
    return int(datetime.now().timestamp() * 1000)
```

**代码解读**：
1. `@mcp.tool()` 在最外层 — FastMCP 将函数注册到工具注册表
2. `@log_tool_call` 在内层 — Python 装饰器从下往上执行，所以 `log_tool_call` 先包装，`mcp.tool()` 再注册
3. 文档字符串是给 LLM 看的"使用说明书"，不是给开发者看的注释。写得越详细，LLM 调用越准确
4. 返回类型 `-> int` 被 FastMCP 用来生成 JSON Schema 的 output schema

### 1.3 带参数的工具：参数设计差异

对比两个 server 中参数类型的不同选择：

| 工具 | 文件:行 | 时间参数类型 | 为什么 |
|------|---------|-------------|--------|
| `search_log` | [cls_server.py:348-353](mcp_servers/cls_server.py#L348-L353) | `int`（毫秒时间戳） | 腾讯云 CLS API 原生使用毫秒时间戳 |
| `query_cpu_metrics` | [monitor_server.py:126-131](mcp_servers/monitor_server.py#L126-L131) | `str`（"YYYY-MM-DD HH:MM:SS"） | 运维人员习惯可读格式 |

**知识点 — 工具参数设计原则**：
MCP 工具的参数应该尽量匹配底层 API/数据源的原始格式，减少转换逻辑。文档字符串中用 `使用示例` 教 LLM 如何构造参数值。

### 1.4 Mock 数据生成模式

**[monitor_server.py:206-234](mcp_servers/monitor_server.py#L206-L234)** — 动态生成 CPU 趋势数据：

```python
base_cpu = 10.0                         # 初始值 10%
while current_time <= end_dt:
    if time_index < 3:
        cpu_value = base_cpu + (time_index * 0.5)   # 前 3 个点缓慢增长
    else:
        growth_factor = (time_index - 2) * 8.5      # 之后快速上升
        cpu_value = min(base_cpu + growth_factor, 96.0)
    cpu_value = round(cpu_value + random.uniform(-2, 2), 1)  # ±2% 随机波动
    # ...
    time_index += 1
```

**代码解读**：
Mock 不是随便返回随机数，而是模拟真实故障场景——CPU 从 10% 逐渐飙升到 95%。这让 Agent 在测试时就能产出有意义的诊断结果。

### 阶段一 练习

1. 手写一个极简 MCP Server 伪代码：
   - 创建 `FastMCP("Demo")` 实例
   - 定义 2 个工具：一个无参（返回字符串），一个有参（接收 `name: str`）
   - `mcp.run(transport="streamable-http", port=8099)`
2. 对比 `@mcp.tool()` 和 `@log_tool_call` 两个装饰器的堆叠顺序，解释为什么 `log_tool_call` 在里面

---

## 阶段二：MCP Client 连接管理（45-90min）⭐⭐⭐

> 理解 Agent 如何连接 MCP Server、获取工具、处理失败。

### 2.1 配置入口

**[app/config.py:57-88](app/config.py#L57-L88)**：

```python
# L59-62 — 单个 Server 的配置字段
mcp_cls_transport: str = "streamable-http"
mcp_cls_url: str = "http://localhost:8003/mcp"
mcp_monitor_transport: str = "streamable-http"
mcp_monitor_url: str = "http://localhost:8004/mcp"

# L77-88 — 组装为 MultiServerMCPClient 需要的格式
@property
def mcp_servers(self) -> Dict[str, Dict[str, Any]]:
    return {
        "cls": {
            "transport": self.mcp_cls_transport,
            "url": self.mcp_cls_url,
        },
        "monitor": {
            "transport": self.mcp_monitor_transport,
            "url": self.mcp_monitor_url,
        }
    }
```

**知识点 — Pydantic Settings**：`BaseSettings` 自动从 `.env` 文件和环境变量读取配置。`mcp_servers` 这个 `@property` 是纯计算属性，不存储到 `.env` 中。

### 2.2 单例客户端 + 初始化流程

**[app/agent/mcp_client.py](app/agent/mcp_client.py)** 完整调用链：

```
get_mcp_client_with_retry()     L158 — 入口，注入重试拦截器
  └→ get_mcp_client()           L112 — 单例守卫
       └→ _create_mcp_client()  L189 — 实际构造
            └→ MultiServerMCPClient(servers, tool_interceptors=[retry_interceptor])
```

逐层代码：

```python
# L17 — 模块级全局变量，单例的存储
_mcp_client: Optional[MultiServerMCPClient] = None

# L158-186 — 带重试的入口
async def get_mcp_client_with_retry(...):
    interceptors = [retry_interceptor]       # L178 — 重试拦截器排第一
    if tool_interceptors:
        interceptors.extend(tool_interceptors)
    return await get_mcp_client(servers=servers, tool_interceptors=interceptors, ...)

# L112-155 — 单例守卫
async def get_mcp_client(...):
    global _mcp_client
    if force_new:
        return _create_mcp_client(servers, tool_interceptors)  # 不缓存
    if _mcp_client is None:                    # L146 — 首次调用才创建
        _mcp_client = _create_mcp_client(...)
    return _mcp_client                         # L155 — 后续调用直接返回

# L189-211 — 工厂函数
def _create_mcp_client(servers, tool_interceptors):
    kwargs = {}
    if tool_interceptors:
        kwargs["tool_interceptors"] = tool_interceptors
    return MultiServerMCPClient(servers, **kwargs)  # L211
```

**知识点 — 为什么用单例**：
AIOps 的 Planner、Executor、Replanner 三个节点都需要 MCP 工具。如果每次新建 `MultiServerMCPClient`，每个都会建立到 8003/8004 的 HTTP 连接池，浪费资源。单例让所有节点共享同一个连接。

### 2.3 重试拦截器

**[app/agent/mcp_client.py:46-102](app/agent/mcp_client.py#L46-L102)**：

```
LLM 决定调用 search_log(topic_id="...", start_time=..., end_time=...)
  │
  ▼
retry_interceptor(request, handler)
  │
  ├─ 第 1 次尝试 ──→ 失败（网络超时）→ 等待 1s (delay * 2^0)
  ├─ 第 2 次尝试 ──→ 失败（服务繁忙）→ 等待 2s (delay * 2^1)
  └─ 第 3 次尝试 ──→ 失败 → 返回 CallToolResult(isError=True, content="...")
                     而不是抛出异常！
```

关键代码：

```python
async def retry_interceptor(request, handler, max_retries=3, delay=1.0):
    for attempt in range(max_retries):              # L73
        try:
            result = await handler(request)          # L79 — 实际调用
            return result
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = delay * (2 ** attempt)   # L92 — 指数退避: 1s, 2s, 4s
                await asyncio.sleep(wait_time)

    # L99-102 — 全部失败后，返回错误结果而非抛异常
    return CallToolResult(
        content=[TextContent(type="text", text=error_msg)],
        isError=True
    )
```

**知识点 — Fail Gracefully（优雅降级）**：
重试 3 次后返回带 `isError=True` 的结果，而不是让异常传播到 Agent 层导致整个诊断流程崩溃。LLM 会看到错误信息并尝试其他方法。

### 2.4 安全加载

**[app/agent/mcp_client.py:35-43](app/agent/mcp_client.py#L35-L43)**：

```python
async def load_mcp_tools_safe(client):
    try:
        tools = await client.get_tools()     # L40
        return tools, None                   # L41 — 成功：(工具列表, None)
    except BaseException as e:
        return [], format_exception_chain(e) # L43 — 失败：(空列表, 错误信息)
```

**知识点 — 元组返回模式**：返回 `(result, error)` 而不是抛异常。调用方（[rag_agent_service.py:126-131](app/services/rag_agent_service.py#L126-L131)）可以决定降级策略——MCP 工具不可用时只用本地工具继续服务，不影响基本对话功能。

### 阶段二 练习

1. 画出 `get_mcp_client_with_retry → get_mcp_client → _create_mcp_client → MultiServerMCPClient` 的完整调用时序
2. `retry_interceptor` 在哪个环节生效？（提示：不是 `get_tools()` 阶段，是 LLM 实际调用工具阶段 — 因为拦截的是 `MCPToolCallRequest`）

---

## 阶段三：MCP + AIOps Agent 集成（60-90min）⭐⭐

> 理解 MCP 工具如何被 Plan-Execute-Replan 三节点消费。

### 3.1 Plan-Execute-Replan 数据流

```
用户输入: "data-sync-service 出现告警，请排查"
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│ Planner (planner.py L62)                                 │
│                                                          │
│ 1. 查询知识库: retrieve_knowledge.ainvoke(input)  L82    │
│ 2. 获取 MCP 工具: mcp_client.get_tools()         L97     │
│ 3. 合并工具: all_tools = local_tools + mcp_tools L100    │
│ 4. 格式化描述: format_tools_description(all_tools) L104  │
│    → LLM 看到:                                          │
│      "- retrieve_knowledge: 从知识库检索..."             │
│      "- get_current_time: 获取当前时间"                  │
│      "- search_log: 基于查询参数搜索日志"                │
│      "- query_cpu_metrics: 查询 CPU 使用率"              │
│      "- query_memory_metrics: 查询内存使用"              │
│ 5. LLM 生成计划:  ["步骤1: 查询 CPU 指标",              │
│                     "步骤2: 查询错误日志", ...]  L126    │
└──────────────────────────┬──────────────────────────────┘
                           │ plan = [步骤1, 步骤2, ...]
                           ▼
         ┌─────────────────────────────────┐
         │  Executor (executor.py L17)      │  ← 循环，每次执行 plan[0]
         │                                  │
         │ 1. task = plan[0]        L33     │
         │ 2. 获取 MCP 工具          L41-42 │
         │ 3. llm.bind_tools(all)   L50     │  ← 真正绑定工具，LLM 可调用
         │ 4. ToolNode(all)         L53     │  ← LangGraph 自动执行工具
         │ 5. LLM 决定调用 search_log →     │
         │    retry_interceptor 拦截 →       │
         │    HTTP POST localhost:8003/mcp   │
         │ 6. 返回: plan[1:], past_steps    │
         └──────────────┬──────────────────┘
                        │
                        ▼
         ┌─────────────────────────────────┐
         │ Replanner (replanner.py L111)    │
         │                                  │
         │ 1. 评估已执行步骤         L124    │
         │ 2. 三种决策:              L194   │
         │    · respond → 生成最终报告      │
         │    · continue → 回到 Executor    │
         │    · replan → 替换剩余计划       │
         └──────────────────────────────────┘
```

### 3.2 关键代码解读

**Planner 中"工具描述"vs Executor 中"工具绑定"**：

```python
# Planner (planner.py L104) — 只把工具信息写成文字给 LLM 读
tools_description = format_tools_description(all_tools)
# → "- search_log: 基于提供的查询参数搜索日志"
# LLM 用这段文字来"规划"要用哪些工具，但不实际调用

# Executor (executor.py L50) — 把工具真正绑定到 LLM
llm_with_tools = llm.bind_tools(all_tools)
# LLM 可以输出 function_call: {name: "search_log", args: {...}}
# 这是真正的 tool calling，会触发实际的 HTTP 请求
```

**知识点 — `bind_tools` vs `format_tools_description`**：
- `format_tools_description`：纯文本描述，用于 Prompt Engineering。LLM 只是"知道"有这些工具，输出的是计划文本。
- `bind_tools`：将工具作为 OpenAI-compatible tool schema 注入。LLM 会输出结构化的 `tool_calls`，框架自动执行。

**ToolNode 的工作原理**（[executor.py:53-83](app/agent/aiops/executor.py#L53-L83)）：

```python
tool_node = ToolNode(all_tools)                    # L53

# L74: LLM 响应中包含 tool_calls
if hasattr(llm_response, "tool_calls") and llm_response.tool_calls:
    messages.append(llm_response)                  # L82
    tool_messages = await tool_node.ainvoke({"messages": messages})  # L83
    # ↑ ToolNode 自动解析 tool_calls，路由到对应工具，执行并返回结果
    messages.extend(tool_messages["messages"])      # L86
    final_response = await llm_with_tools.ainvoke(messages)  # L87
    # ↑ 将工具结果再送回 LLM 生成最终回答
```

**知识点 — ToolNode**：LangGraph 的内置节点类型。收到 LLM 的 `tool_calls` 后，自动匹配工具名 → 调用工具 → 收集结果。不管是本地工具还是 MCP 工具，对它来说都是 `BaseTool` 对象，调用方式完全统一。

### 3.3 状态管理

**[app/agent/aiops/state.py](app/agent/aiops/state.py) L10-24**：

```python
class PlanExecuteState(TypedDict):
    input: str                              # 用户原始输入
    plan: List[str]                         # 剩余待执行的步骤
    past_steps: Annotated[List[tuple], operator.add]  # ← 关键！追加而非覆盖
    response: str                           # 最终响应
```

**知识点 — `Annotated[List, operator.add]`**：
LangGraph 中每个节点返回的 dict 会 merge 到 state。对于 `past_steps` 字段，`operator.add` 表示用 `list1 + list2` 的方式合并（追加），而不是覆盖。这样每轮 Executor 执行一个步骤后，`[(step1, result1)] + [(step2, result2)] = [(step1, result1), (step2, result2)]`。

### 阶段三 练习

1. 追踪一次完整的 AIOps 诊断：从 Planner L96 获取 MCP 工具 → Executor L41 获取 MCP 工具 → Replanner L142 获取 MCP 工具。为什么三个节点都重复调用 `get_mcp_client_with_retry()`？单例模式保证了什么？
2. 如果 `search_log` 调用时 MCP Server 崩溃，`retry_interceptor` 会如何处理？Executor 会崩溃吗？

---

## 阶段四：MCP + RAG Agent 集成（45-60min）⭐⭐

> 对比 ReAct 模式下 MCP 集成的不同策略。

### 4.1 两种 Agent 模式的 MCP 集成对比

```
AIOps Agent (Plan-Execute-Replan)         RAG Agent (ReAct)
──────────────────────────────────        ──────────────────
Planner → 获取 MCP 工具列表               用户提问
  ↓                                           ↓
Executor → 绑定 MCP 工具、逐步骤执行        create_agent(model, tools=all_tools)
  ↓                                           ↓
Replanner → 获取 MCP 工具、决策            LLM 自主推理-行动循环
  ↓                                           ↓
返回报告                                   流式输出回答

MCP 工具加载: 直接 get_tools()            MCP 工具加载: load_mcp_tools_safe()
错误处理: 拦截器兜底                       错误处理: 安全降级到仅本地工具
Transport 校验: 无                         Transport 校验: suggest_mcp_transport()
```

### 4.2 RAG Agent 初始化流程

**[app/services/rag_agent_service.py:112-149](app/services/rag_agent_service.py#L112-L149)**：

```python
async def _initialize_agent(self):
    if self._agent_initialized:                    # L114 — 只初始化一次
        return

    # L117-123 — Transport 配置校验（AIOps 没有这一步）
    for name, server in config.mcp_servers.items():
        hint = suggest_mcp_transport(url, transport)
        if hint:
            logger.warning(f"MCP 配置 [{name}]: {hint}")
        # ↑ 例如：URL 含 /sse 但配置了 streamable-http → 输出警告

    # L125-133 — 安全加载（AIOps 不使用 safe 版本）
    mcp_client = await get_mcp_client_with_retry()
    mcp_tools, mcp_err = await load_mcp_tools_safe(mcp_client)
    if mcp_err:
        logger.warning("MCP 工具加载失败，将仅使用本地工具继续运行")
        self.mcp_tools = []                        # L131 — 降级：只用本地工具
    else:
        self.mcp_tools = mcp_tools

    # L136-142 — 合并工具，创建 ReAct Agent
    all_tools = self.tools + self.mcp_tools
    self.agent = create_agent(self.model, tools=all_tools, ...)
```

**知识点 — `create_agent` vs 手写 Plan-Execute-Replan**：
- `create_agent`（[rag_agent_service.py:138](app/services/rag_agent_service.py#L138)）：LangChain 内置的 ReAct Agent 工厂。LLM 自主决定何时调用工具、调用哪个工具，没有固定的 Plan 结构。适合开放的对话场景。
- Plan-Execute-Replan：自定义三节点图。LLM 先生成计划再逐步执行，中间有评估环节。适合结构化的运维诊断场景。

### 4.3 Transport 不匹配检测

**[app/agent/mcp_client.py:214-230](app/agent/mcp_client.py#L214-L230)**：

```python
def suggest_mcp_transport(url: str, transport: str) -> str | None:
    # 场景1: URL 含 /sse，但配置为 streamable-http → 应该用 sse
    if "/sse" in url and transport in ("streamable-http", "http"):
        return "腾讯云等托管端点应使用 transport=sse"

    # 场景2: URL 含 /mcp 但无 /sse，配置为 sse → 应该用 streamable-http
    if transport == "sse" and "/mcp" in url and "/sse" not in url:
        return "本地服务通常应使用 transport=streamable-http"

    return None  # 无问题
```

**知识点**：这是一个启发式检测函数，不修改配置，只输出警告。防止开发者配置错 transport 类型导致连接失败。

### 阶段四 练习

1. 对比 AIOps Agent 和 RAG Agent 中 MCP 集成的 5 个维度差异（模式/加载/错误/绑定/校验）
2. 如果两台 MCP Server 都不可用，RAG Agent 用户会看到什么？提示：走 [rag_agent_service.py:127-131](app/services/rag_agent_service.py#L127-L131) 的降级路径

---

## 阶段五：进阶主题（30-60min）

### 5.1 新增 MCP Server 的标准流程

假设要新增一个 Redis 缓存查询 MCP Server：

```
步骤1: 新建 mcp_servers/redis_server.py
      └→ 仿照 cls_server.py 模式:
         mcp = FastMCP("Redis")
         @mcp.tool()
         def query_cache(key: str) -> Dict: ...
         mcp.run(transport="streamable-http", port=8005)

步骤2: 修改 app/config.py
      └→ 添加:
         mcp_redis_transport: str = "streamable-http"
         mcp_redis_url: str = "http://localhost:8005/mcp"
      └→ 在 mcp_servers property 中添加 "redis" 条目

步骤3: 修改 .env（可选，使用默认值可跳过）
      └→ MCP_REDIS_URL=http://localhost:8005/mcp
```

无需修改 `mcp_client.py`——`MultiServerMCPClient` 自动读取 config 中的所有 server 条目。

### 5.2 Mock → 真实 API 升级路径

[mcp_servers/README.md L97-113](mcp_servers/README.md#L97-L113)：

当前 `search_log` 等工具返回 mock 数据。接入真实腾讯云 CLS SDK 只需要：

```python
# 当前 (mock):
def search_log(topic_id, start_time, end_time, ...):
    return {"logs": [...mock data...]}

# 升级后 (真实 API):
from tencentcloud.cls.v20201016 import cls_client

def search_log(topic_id, start_time, end_time, ...):
    resp = cls_client.SearchLog(...)
    return {"logs": resp.logs}  # 保持返回格式不变
```

**知识点**：保持函数签名和返回格式不变，Agent 层（Planner/Executor）无需任何改动——这就是 MCP 作为抽象层的价值。

### 5.3 完整数据流 Trace

```
用户: POST /api/aiops → aiops.py
  → aiops_service.py: 构建 PlanExecuteState Graph
    → planner.py:98   mcp_client = get_mcp_client_with_retry()
    → planner.py:99   mcp_tools = await mcp_client.get_tools()
                       └→ MultiServerMCPClient 向 localhost:8003/mcp + localhost:8004/mcp
                          发送 MCP 协议的 list_tools 请求
    → planner.py:104  format_tools_description(all_tools)
    → planner.py:123  LLM 生成 Plan

    → executor.py:41  mcp_client = get_mcp_client_with_retry()  ← 同一个单例
    → executor.py:42  mcp_tools = await mcp_client.get_tools()  ← 从缓存返回
    → executor.py:50  llm.bind_tools(all_tools)
    → executor.py:74  LLM 决定: function_call(name="search_log", args={...})
    → executor.py:83  ToolNode.ainvoke()
        → retry_interceptor(request, handler)  ← 拦截
          → handler(request)                   ← 实际 HTTP 调用
            → POST http://localhost:8003/mcp
              body: {"method": "tools/call", "params": {"name": "search_log", ...}}
            ← cls_server.py:348 search_log() 执行
            ← 返回 {"logs": [...], "total": N, ...}
          → CallToolResult(content=[...])
        → ToolNode 将结果添加到 messages
    → executor.py:87  LLM 根据工具结果生成回答

    → replanner.py:142  mcp_client = get_mcp_client_with_retry()
    → replanner.py:143  mcp_tools = await mcp_client.get_tools()
    → replanner.py:194  决策: respond → _generate_response()
    → SSE 流输出最终报告给前端
```

---

## 学习检查清单

- [ ] 能画出 MCP Server ↔ Client ↔ Agent 三层架构图
- [ ] 能手写 FastMCP 最小骨架（创建 + `@mcp.tool()` + `mcp.run()`）
- [ ] 理解 `@mcp.tool()` 装饰器 + 文档字符串 → LLM 工具 Schema 的转换
- [ ] 能解释 `get_mcp_client_with_retry` 的调用链和单例机制
- [ ] 理解 `retry_interceptor` 的指数退避 + graceful degradation 设计
- [ ] 能区分 `format_tools_description`（文本）和 `bind_tools`（绑定）的用途
- [ ] 能对比 AIOps Agent 和 RAG Agent 两种 MCP 集成模式
- [ ] 理解 `load_mcp_tools_safe` 的安全降级策略
- [ ] 能独立完成"新增一个 MCP Server"的 3 步操作
- [ ] 能从 POST /api/aiops 一路 tracedown 到 cls_server.py 的工具函数

## 关键文件速查

| 文件 | 核心内容 | 优先级 |
|------|---------|--------|
| [mcp_servers/cls_server.py](mcp_servers/cls_server.py) | FastMCP 工具定义、日志装饰器、Mock 模式 | ⭐⭐⭐ |
| [app/agent/mcp_client.py](app/agent/mcp_client.py) | 单例 Client、重试拦截器、安全加载 | ⭐⭐⭐ |
| [app/config.py](app/config.py) L57-88 | MCP transport/URL 配置 | ⭐⭐ |
| [app/agent/aiops/executor.py](app/agent/aiops/executor.py) | ToolNode、bind_tools 实战 | ⭐⭐ |
| [app/agent/aiops/planner.py](app/agent/aiops/planner.py) | format_tools_description 使用 | ⭐⭐ |
| [app/agent/aiops/replanner.py](app/agent/aiops/replanner.py) | MCP 工具在决策中的使用 | ⭐⭐ |
| [app/services/rag_agent_service.py](app/services/rag_agent_service.py) L112-149 | ReAct + safe load 集成 | ⭐⭐ |
| [app/agent/aiops/state.py](app/agent/aiops/state.py) | PlanExecuteState 定义 | ⭐ |
| [app/agent/aiops/utils.py](app/agent/aiops/utils.py) | format_tools_description 实现 | ⭐ |
| [mcp_servers/monitor_server.py](mcp_servers/monitor_server.py) | 动态 Mock 数据生成 | ⭐ |
| [app/tools/__init__.py](app/tools/__init__.py) | 本地工具 vs MCP 工具的边界 | ⭐ |
| [mcp_servers/README.md](mcp_servers/README.md) | MCP 服务文档 | ⭐ |
