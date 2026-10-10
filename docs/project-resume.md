# SuperBizAgent — 企业级智能运维助手

## 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | ≥ 3.11 |
| Web 框架 | FastAPI + Uvicorn + SSE (sse-starlette) | ≥ 0.109 |
| Agent 框架 | LangChain + LangGraph | ≥ 0.1.0 / ≥ 0.0.40 |
| LLM 接入 | langchain-openai (兼容模式) + dashscope + openai | — |
| LLM 后端 | 阿里云 DashScope (通义千问) / 火山方舟 / OpenAI 兼容 | — |
| Embedding | DashScope text-embedding-v4 / 火山方舟 doubao-embedding-vision | — |
| 向量数据库 | Milvus (pymilvus + langchain-milvus) | ≥ 2.3.5 |
| 文档分割 | langchain-text-splitters | ≥ 1.1.0 |
| 工具协议 | MCP: fastmcp + langchain-mcp-adapters | ≥ 2.14 / ≥ 0.2.1 |
| 配置管理 | pydantic-settings + python-dotenv | ≥ 2.1.0 |
| 日志 | Loguru | ≥ 0.7.2 |
| 容器化 | Docker Compose (Milvus + etcd + MinIO + Attu) | — |
| 前端 | 原生 HTML/CSS/JS + marked.js + highlight.js | — |

---

## 项目简介

SuperBizAgent 是一个面向企业运维场景的 AI Agent 系统，以 **RAG 知识库问答**和 **AIOps 自动故障诊断**为双核心，打通从运维文档查阅到实时故障排查的完整链路——"接收请求 → 理解意图 → 调度工具/检索知识 → 生成结果"。

## 核心能力

- **RAG 智能对话**：基于 Milvus 向量库 + 多 Provider Embedding，支持流式 Markdown 输出；消息历史自动修剪 + 会话持久化
- **AIOps 自动诊断**：Plan-Execute-Replan 三阶段状态机，一键触发 → 获取告警 → 查日志 → 分析指标 → 生成诊断报告
- **MCP 工具协议**：自建 CLS 日志查询 + Monitor 监控数据两个 MCP Server，Agent 可远程调用运维工具
- **多 Provider 切换**：LLM 工厂统一 DashScope / 火山方舟 / OpenAI 兼容接口，配置即可切换
- **文档上传即索引**：三阶段文档分割管线（Markdown 标题分割 → 递归字符分割 → 小片段合并），自动建立向量索引

## 技术架构

| 分层 | 技术选型 | 职责 |
|------|---------|------|
| 接入层 | FastAPI + Uvicorn + SSE | 异步 HTTP、流式事件推送、Web 界面 |
| 服务层 | LangGraph StateGraph | RAG Agent 编排 + AIOps 诊断图编译 |
| Agent 引擎 | Planner / Executor / Replanner + ToolNode | 诊断计划制定 → 工具自动调用 → 结果评估 |
| 工具协议 | MCP + FastMCP (`mcp_servers/`) | CLS 日志服务(8003) + Monitor 监控服务(8004) |
| 向量存储 | Milvus 2.5 + Docker Compose | 文档分片 CRUD + 相似度检索 |
| 基础设施 | Loguru + Pydantic Settings | 日志按天轮转、多 Provider 配置中心 |

## 技术亮点

**Plan-Execute-Replan 诊断引擎**

自定义 LangGraph 三节点闭环：Planner 检索知识库经验 + 感知全部可用工具（本地+MCP），LLM 生成 4~6 步诊断计划；Executor 通过 `ToolNode` 自动完成"决策→调工具→消化结果"三步；Replanner 做三态决策（continue/replan/respond），内置最多 8 步硬限制防死循环。

**MCP 客户端容错设计**

`MultiServerMCPClient` 全局单例管理多 Server 连接；工具调用通过指数退避重试拦截器（1s→2s→4s，最多 3 次）实现容错；全部失败时返回 `isError=True` 而非抛异常，保证诊断流程不因单个工具故障中断。MCP 不可用时 Agent 自动降级为仅本地工具。

**RAG 消息管理**

`MemorySaver` 实现会话级对话持久化，`trim_messages_middleware` 自动修剪超长上下文——保留首条 System Message + 最近 6~7 条消息，防止 LLM 上下文窗口溢出。

**工具体系**

本地工具（知识检索 + 时间 + Prometheus 告警）与 MCP 远程工具（CLS 日志 + Monitor 监控）动态合并，LLM 通过 `bind_tools` 统一感知和调用，`ToolNode` 自动路由执行，对 Agent 而言两类工具透明。

## 项目规模

- 代码量：~9,000 行 Python，32 篇技术文档
- 核心模块：4 层架构、15+ 服务/引擎模块、7 个 MCP 工具
- API 端点：5 个（普通对话 / 流式对话 / AIOps 诊断 / 文件上传 / 多模态 Embedding）
- 依赖：Python ≥ 3.11，LangChain ≥ 0.1.0，LangGraph ≥ 0.0.40，fastmcp ≥ 2.14.0

## 目录结构

```
super_biz_agent/
├── app/                    # 应用核心
│   ├── api/                # HTTP 路由（chat / aiops / file / embedding / health）
│   ├── services/           # 业务编排（RAG Agent / AIOps / 文档分割 / Embedding / 向量存储）
│   ├── agent/              # Agent 引擎（mcp_client / planner / executor / replanner）
│   ├── tools/              # 本地工具集
│   ├── core/               # 基础设施（LLM 工厂 / Milvus 客户端）
│   └── models/             # Pydantic 数据模型
├── mcp_servers/            # MCP 工具服务（CLS 日志 / Monitor 监控）
├── static/                 # Web 前端（原生 HTML/CSS/JS + marked.js）
├── aiops-docs/             # 运维知识库（Markdown 源文档）
└── vector-database.yml     # Milvus + etcd + MinIO + Attu 容器编排
```
