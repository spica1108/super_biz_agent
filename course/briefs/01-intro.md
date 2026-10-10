# Module 1: The Big Picture — What Happens When You Click "Diagnose"

## Teaching Arc
- **Metaphor:** A detective arriving at a crime scene — survey the situation, form a theory, gather evidence, revise the theory, write the report
- **Opening hook:** You've used AI chatbots before. You type a question, you get an answer. But SuperBizAgent's AIOps mode is different — it doesn't just answer. It *investigates*. Let's trace what actually happens when someone clicks that "Diagnose" button.
- **Key insight:** The app follows a Plan → Execute → Replan cycle — an AI that thinks ahead, acts, then re-evaluates, just like a human troubleshooter
- **"Why should I care?":** Understanding the full journey from click to report lets you see where things can go wrong, and helps you ask AI assistants to build similar "planning" systems

## Code Snippets (pre-extracted)

**File: app/main.py (lines 77-88)** — The root route
```python
@app.get("/")
async def root():
    """返回首页"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "message": f"Welcome to {config.app_name} API",
        "version": config.app_version,
        "docs": "/docs"
    }
```

**File: app/api/aiops.py (lines 1-40, the whole file)** — The AIOps endpoint
Read from file: app/api/aiops.py

**File: app/services/aiops_service.py (lines 20-28)** — Service init
```python
class AIOpsService:
    """通用 Plan-Execute-Replan 服务"""

    def __init__(self):
        """初始化服务"""
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()
        logger.info("Plan-Execute-Replan Service 初始化完成")
```

## Interactive Elements

- [x] **Data flow animation** — Actors: Browser, FastAPI, AIOpsService, Planner. Steps trace the diagnosis request from browser click → HTTP request → route handler → AIOps service → Planner node. 5 steps.
- [x] **Code↔English translation** — The root route snippet (app/main.py lines 77-88), showing how FastAPI serves the web UI
- [ ] **Quiz** — Scenario: "A user reports the page loads but shows a JSON response instead of the UI. Based on what you just learned, what's the most likely cause?" (tests understanding of FileResponse fallback vs. static file serving)
- [ ] **Group chat animation** — NOT in this module (data flow animation instead)
- [x] **Pattern cards** — 3 cards: "Plan-Execute-Replan" pattern, "Streaming output", "Tool integration"

## Reference Files to Read
- `references/interactive-elements.md` → "Data Flow Animation", "Code ↔ English Translation Blocks", "Pattern/Feature Cards", "Scenario Quiz", "Glossary Tooltips"
- `references/content-philosophy.md` → ALL
- `references/gotchas.md` → ALL

## Connections
- **Previous module:** None (first module)
- **Next module:** Module 2 "Meet the Cast" — will introduce each component individually, building on the end-to-end tracing here
- **Tone/style notes:** Teal accent (#2A7B9B). Actor naming: use descriptive names like "Browser", "FastAPI", "AIOpsService", "Planner". Module bg: var(--color-bg) (even module).
