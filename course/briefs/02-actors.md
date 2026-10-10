# Module 2: Meet the Cast — Every Component Has One Job

## Teaching Arc
- **Metaphor:** A hospital emergency room team — the triage nurse (API routes), the attending physician (AIOps Service), the specialists (Planner/Executor/Replanner), and the lab techs (MCP tools). Everyone has exactly one job, and they communicate through clear handoffs.
- **Opening hook:** In Module 1, we saw the whole diagnosis flow at 30,000 feet. Now let's land the plane and meet each member of the team individually.
- **Key insight:** Software works because responsibilities are split across focused components. Each piece is simple on its own — the complexity only emerges from how they coordinate.
- **"Why should I care?":** When you tell an AI coding tool "add a new feature," you need to know WHICH component to put it in. Putting audit logging in the API route is wrong — it belongs in a service. Knowing the cast lets you give precise instructions.

## Code Snippets (pre-extracted)

**File: app/config.py (lines 11-28)** — Settings class
```python
class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用配置
    app_name: str = "SuperBizAgent"
    app_version: str = "1.0.0"
    debug: bool = False
    allow_missing_external_services: bool = False
    host: str = "0.0.0.0"
    port: int = 9900
```

**File: app/main.py (lines 49-71)** — FastAPI app creation and route registration
```python
# 创建 FastAPI 应用
app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description="基于 LangChain 的智能oncall运维系统",
    lifespan=lifespan
)

# 配置 CORS,允许任意来源访问 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health.router, tags=["健康检查"])
app.include_router(chat.router, prefix="/api", tags=["对话"])
app.include_router(file.router, prefix="/api", tags=["文件管理"])
app.include_router(aiops.router, prefix="/api", tags=["AIOps智能运维"])
app.include_router(embedding.router, prefix="/api", tags=["Embedding"])
```

**File: app/tools/__init__.py (first 10 lines)** — Tool exports
```python
from app.tools.knowledge_tool import retrieve_knowledge
from app.tools.time_tool import get_current_time
from app.tools.query_metrics_alerts import query_prometheus_alerts

DEFAULT_LOCAL_AGENT_TOOLS = [
    retrieve_knowledge,
    get_current_time,
    query_prometheus_alerts
]
```

## Interactive Elements

- [x] **Group chat animation** — Actors: "Browser" (actor-1), "FastAPI Router" (actor-2), "AIOpsService" (actor-3), "Planner" (actor-4), "MCP Tool" (actor-5). 6-8 messages showing a diagnosis request being routed through each component. Each message reveals what role that component plays.
- [x] **Code↔English translation** — The route registration snippet (app/main.py lines 49-71), explaining how FastAPI connects URLs to handlers
- [x] **Visual file tree** — Show key directories with annotations: app/api, app/services, app/agent, app/tools, mcp_servers — each with a one-line plain-English job description
- [x] **Quiz** — 3 questions, scenario-style: "You want to add a new tool that checks server disk space. Where should you create it?" Options: app/api/disk.py, app/tools/disk_tool.py, app/services/disk_service.py, mcp_servers/disk_server.py. (Two answers are defensible — the quiz should explain the tradeoff between local tools and MCP servers.)
- [ ] **Data flow animation** — NOT here (already in Module 1)

## Reference Files to Read
- `references/interactive-elements.md` → "Group Chat Animation", "Code ↔ English Translation Blocks", "Visual File Tree", "Multiple-Choice Quizzes", "Scenario Quiz", "Glossary Tooltips", "Icon-Label Rows"
- `references/content-philosophy.md` → ALL
- `references/gotchas.md` → ALL

## Connections
- **Previous module:** Module 1 "The Big Picture" — traced end-to-end flow. This module zooms into each component.
- **Next module:** Module 3 "The Plan-Execute-Replan Loop" — deep dive into the coordination mechanism between Planner/Executor/Replanner
- **Tone/style notes:** Teal accent. Actor colors: Browser=actor-1(vermillion), FastAPI=actor-2(teal), AIOpsService=actor-3(plum), Planner=actor-4(amber), MCP=actor-5(forest). Module bg: var(--color-bg-warm) (odd module).
