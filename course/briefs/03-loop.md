# Module 3: The Plan-Execute-Replan Loop — Think, Act, Evaluate, Repeat

## Teaching Arc
- **Metaphor:** A chess player thinking several moves ahead — but unlike chess, you get to see the board after each move and change your strategy. The Planner is like studying the board and forming a strategy. The Executor is moving a piece. The Replanner is looking at the new board state and deciding: "Is my strategy still good? Do I need to pivot? Or have I already won?"
- **Opening hook:** Module 1 showed us the loop exists. Module 2 introduced the players. Now watch them actually *play the game* — here's the three-step dance that turns a vague "something's wrong" into a detailed diagnostic report.
- **Key insight:** The Replanner is the magic. Most AI systems follow a rigid plan. This one *adapts* — it can abandon bad steps mid-investigation and try something else. That's what makes it feel almost human.
- **"Why should I care?":** The Plan-Execute-Replan pattern is one of the most powerful AI agent design patterns. If you can explain it, you can ask AI to build it for any domain — legal research, market analysis, recruitment screening.

## Code Snippets (pre-extracted)

**File: app/agent/aiops/state.py (lines 1-24)** — State definition
```python
class PlanExecuteState(TypedDict):
    """Plan-Execute-Replan 状态"""
    
    # 用户输入（任务描述）
    input: str
    
    # 执行计划（步骤列表）
    plan: List[str]
    
    # 已执行的步骤历史
    # 使用 operator.add 实现追加式更新（而非覆盖）
    past_steps: Annotated[List[tuple], operator.add]
    
    # 最终响应/报告
    response: str
```

**File: app/agent/aiops/planner.py (lines 62-80, key part)** — Planner function
```python
async def planner(state: PlanExecuteState) -> Dict[str, Any]:
    """规划节点：根据用户输入生成执行计划"""
    logger.info("=== Planner：制定执行计划 ===")
    input_text = state.get("input", "")
    
    try:
        # 步骤1: 查询内部文档获取相关经验
        experience_docs = ""
        try:
            context_str = await retrieve_knowledge.ainvoke({"query": input_text})
            if context_str and context_str.strip():
                experience_docs = context_str
        except Exception as e:
            logger.warning(f"查询内部文档失败: {e}")
        
        # ... tool gathering and LLM call ...
        plan_result = await planner_chain.ainvoke({...})
        return {"plan": plan_steps}
```

**File: app/agent/aiops/executor.py (lines 17-44)** — Executor core
```python
async def executor(state: PlanExecuteState) -> Dict[str, Any]:
    plan = state.get("plan", [])
    if not plan:
        return {}
    task = plan[0]
    # ... tool setup ...
    llm_with_tools = llm.bind_tools(all_tools)
    tool_node = ToolNode(all_tools)
    # LLM decides which tools to call, then ToolNode executes them
    llm_response = await llm_with_tools.ainvoke(messages)
    if hasattr(llm_response, "tool_calls") and llm_response.tool_calls:
        tool_messages = await tool_node.ainvoke({"messages": messages})
        # ... generate final answer with tool results ...
    return {"plan": plan[1:], "past_steps": [(task, result)]}
```

**File: app/agent/aiops/replanner.py (lines 111-135, 160-196)** — Replanner decision logic
```python
async def replanner(state: PlanExecuteState) -> Dict[str, Any]:
    input_text = state.get("input", "")
    plan = state.get("plan", [])
    past_steps = state.get("past_steps", [])
    
    # 强制限制：已执行步骤过多，直接生成响应
    MAX_STEPS = 8
    if len(past_steps) >= MAX_STEPS:
        return await _generate_response(state, llm)
    
    if plan:
        act = await replanner_chain.ainvoke({...})
        if action == "respond":
            return await _generate_response(state, llm)
        elif action == "replan":
            if len(past_steps) >= 5:
                return await _generate_response(state, llm)
            return {"plan": new_steps}
        else:  # continue
            return {}
```

**File: app/services/aiops_service.py (lines 29-78)** — Graph construction
```python
def _build_graph(self):
    workflow = StateGraph(PlanExecuteState)
    workflow.add_node("planner", planner)
    workflow.add_node("executor", executor)
    workflow.add_node("replanner", replanner)
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "executor")
    workflow.add_edge("executor", "replanner")
    
    def should_continue(state: PlanExecuteState) -> str:
        if state.get("response"):
            return END
        if state.get("plan"):
            return "executor"
        return END
    
    workflow.add_conditional_edges("replanner", should_continue, {
        "executor": "executor", END: END
    })
    return workflow.compile(checkpointer=self.checkpointer)
```

## Interactive Elements

- [x] **Group chat animation** — Actors: Planner, Executor, Replanner in an iMessage-style group chat. They discuss a diagnosis task step by step. 8-10 messages. Planner: "I've made a plan: 1) Check CPU, 2) Query logs, 3) Check memory, 4) Generate report." Executor: "Running step 1... CPU is at 95%!" Replanner: "Interesting. Let's skip memory and dig deeper into CPU — plan updated."
- [x] **Code↔English translation** — Two translation blocks: (1) the State class showing how data flows through the loop, (2) the graph construction showing how nodes are wired together
- [x] **Data flow animation** — Actors: State, Planner, Executor, Replanner, Tools. 6 steps tracing the flow of `plan`, `past_steps`, and `response` through the graph nodes, with visual packet animation between each node
- [x] **Quiz** — 3 scenario questions: (1) "The Executor failed 3 times on a tool call. What does the Replanner do?" (2) "You're on step 7 of a 4-step plan (because the Replanner added steps). What happens next?" (tests MAX_STEPS limit knowledge) (3) "What would happen if we removed the Replanner and just did Plan → Execute all steps → Report?"
- [x] **Callout box** — "This pattern — Plan-Execute-Replan — is one of the most important AI agent architectures. It's what separates 'chatbots that answer questions' from 'agents that solve problems.'"

## Reference Files to Read
- `references/interactive-elements.md` → "Group Chat Animation", "Data Flow Animation", "Code ↔ English Translation Blocks", "Multiple-Choice Quizzes", "Scenario Quiz", "Callout Boxes", "Glossary Tooltips"
- `references/content-philosophy.md` → ALL
- `references/gotchas.md` → ALL

## Connections
- **Previous module:** Module 2 "Meet the Cast" — introduced Planner, Executor, Replanner as individuals. This module shows them collaborating.
- **Next module:** Module 4 "The Outside World" — the tools that Executor calls (MCP servers, Milvus, DashScope LLM)
- **Tone/style notes:** Teal accent. Actor colors match Module 2: Planner=amber, Executor=vermillion, Replanner=teal. This is the most important module — make the dance between the three nodes crystal clear. Module bg: var(--color-bg) (even module).
