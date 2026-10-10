# Module 4: The Outside World — APIs, Databases, and Why They Fail

## Teaching Arc
- **Metaphor:** A journalist writing a story. They don't know everything — they call sources (APIs), check archives (vector database), and consult experts (LLM). Each source can be slow, unavailable, or give misleading information. A good journalist cross-references and knows when a source is unreliable.
- **Opening hook:** So far, we've been inside the app's brain. But the app doesn't think in a vacuum — it reaches out to three external services for help. Each one is a potential failure point, and the app has to handle that gracefully.
- **Key insight:** External dependencies are your biggest source of bugs and unreliability. The app knows this and has built-in defenses — retries, timeouts, graceful degradation (running in "degraded mode" when Milvus is down).
- **"Why should I care?":** When you're building with AI, you'll constantly be choosing external services. Understanding their failure modes — rate limits, timeouts, downtime — and how to defend against them is what separates hobby projects from production apps.

## Code Snippets (pre-extracted)

**File: app/config.py (lines 29-32, 44-46, 57-62)** — External service config
```python
    # DashScope 配置
    dashscope_api_key: str = ""
    dashscope_model: str = "qwen-max"
    dashscope_embedding_model: str = "text-embedding-v4"

    # Milvus 配置
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_timeout: int = 10000  # 毫秒

    # MCP 服务配置
    mcp_cls_transport: str = "streamable-http"
    mcp_cls_url: str = "http://localhost:8003/mcp"
    mcp_monitor_transport: str = "streamable-http"
    mcp_monitor_url: str = "http://localhost:8004/mcp"
```

**File: app/main.py (lines 29-46)** — Graceful degradation on startup
```python
    # 连接 Milvus
    logger.info("🔌 正在连接 Milvus...")
    try:
        milvus_manager.connect()
        logger.info("✅ Milvus 连接成功")
    except Exception as e:
        if not config.allow_missing_external_services:
            raise
        logger.warning(f"Milvus 暂不可用，开发降级模式继续启动: {e}")
```

**File: app/agent/mcp_client.py (lines 1-60)** — MCP client with retry
Key concept: get_mcp_client_with_retry() uses exponential backoff (3 attempts), load_mcp_tools_safe() catches errors and returns empty list so the app keeps running even if MCP servers are down.

**File: app/core/llm_factory.py (key section)** — LLM factory
Shows how the factory creates ChatOpenAI instances routed to either DashScope or Volcengine based on llm_provider config.

**File: app/services/vector_search_service.py (key section)** — Milvus search
Shows LangChain's Milvus vector store similarity_search with top_k parameter.

## Interactive Elements

- [x] **Architecture diagram** — Three zones: "External LLM (DashScope)", "Vector Database (Milvus)", "MCP Tools (CLS + Monitor)". Clickable components with descriptions of what each provides and its failure modes.
- [x] **Code↔English translation** — The graceful degradation snippet (app/main.py lines 29-46), showing the try/except pattern that keeps the app alive when Milvus is down
- [x] **Group chat animation** — NOT in this module (architecture diagram instead)
- [x] **Data flow animation** — NOT in this module
- [x] **Quiz** — 3 scenario questions: (1) "Milvus is down. A user asks a RAG question. What happens?" (2) "DashScope API returns a rate limit error on the 3rd retry. What should the MCP client do?" (3) "You're choosing between a local tool and an MCP server for a new feature. Which factors matter?" (tradeoff question)
- [x] **Callout box** — "The external dependency rule: Every external service WILL fail at some point. The question isn't 'will it fail?' but 'what does our app do when it fails?'"

## Reference Files to Read
- `references/interactive-elements.md` → "Interactive Architecture Diagram", "Code ↔ English Translation Blocks", "Multiple-Choice Quizzes", "Scenario Quiz", "Callout Boxes", "Glossary Tooltips", "Badge List"
- `references/content-philosophy.md` → ALL
- `references/gotchas.md` → ALL

## Connections
- **Previous module:** Module 3 "The Loop" — showed Executor calling tools. This module shows what those tools actually connect to.
- **Next module:** Module 5 "The Safety Nets" — the guardrails and defensive patterns that protect the system from external failures
- **Tone/style notes:** Teal accent. This module should feel concrete and practical — specific configs, specific failure modes. Module bg: var(--color-bg-warm) (odd module).
