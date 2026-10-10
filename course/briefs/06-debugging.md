# Module 6: When Things Go Wrong — Debugging an AI Agent System

## Teaching Arc
- **Metaphor:** A flight data recorder (black box). When a plane has an incident, investigators don't guess — they pull the black box and replay every sensor reading, every control input, every system state leading up to the incident. Debugging an AI agent system is the same: follow the trail of state changes through each node.
- **Opening hook:** You've built a mental model of how this system works. Now let's use it. Here are three real scenarios where something went wrong — and your job is to figure out what happened, which component is responsible, and how to fix it.
- **Key insight:** Debugging AI agents is different from debugging regular code. The bug isn't a typo — it's usually a decision the AI made that was reasonable in isolation but wrong in context. You debug by tracing the state through the graph, not by reading code line by line.
- **"Why should I care?":** This is the skill that actually saves you when you're building with AI. Knowing how to trace state through a graph is the difference between "it's broken and I don't know why" and "the Replanner chose 'replan' when it should have chosen 'respond' — I need to adjust the prompt."

## Code Snippets (pre-extracted)

**File: app/agent/aiops/replanner.py (lines 44-88)** — Replanner prompt (the full system prompt)
Shows the decision logic: respond > continue > replan. This is the most likely source of bugs — prompt engineering, not code logic.

**File: app/services/aiops_service.py (lines 48-72)** — Conditional edges
```python
        def should_continue(state: PlanExecuteState) -> str:
            """判断是否继续执行"""
            if state.get("response"):
                logger.info("已生成最终响应，结束流程")
                return END
            plan = state.get("plan", [])
            if plan:
                logger.info(f"继续执行，剩余 {len(plan)} 个步骤")
                return "executor"
            logger.info("计划执行完毕，生成最终响应")
            return END

        workflow.add_conditional_edges(
            "replanner", should_continue,
            {"executor": "executor", END: END}
        )
```

**File: app/agent/aiops/executor.py (lines 102-107)** — Error handling in executor
```python
    except Exception as e:
        logger.error(f"执行步骤失败: {e}", exc_info=True)
        return {
            "plan": plan[1:],
            "past_steps": [(task, f"执行失败: {str(e)}")],
        }
```

**File: app/services/rag_agent_service.py (lines 309-313)** — Error yield in streaming
```python
        except Exception as e:
            detail = format_exception_chain(e)
            logger.error(f"[会话 {session_id}] RAG Agent 查询失败（流式）: {detail}")
            yield {"type": "error", "data": detail}
```

## Interactive Elements

- [x] **Scenario quiz** — 3 debugging scenarios with detailed context blocks:
  1. "The diagnosis runs forever and never produces a report." (MAX_STEPS missing or Replanner always chooses 'replan')
  2. "The diagnosis skips important steps and gives a superficial report after just 2 tool calls." (Replanner too aggressive with 'respond', Replanner prompt needs adjustment)
  3. "The Executor keeps failing on step 1 but the system continues to step 2 anyway with bad data." (Error handling in executor returns result even on failure, past_steps includes failure message but the Replanner might ignore it)
- [x] **Code↔English translation** — The should_continue conditional edge — explain how this tiny function is the traffic controller for the entire loop
- [x] **Flow diagram** — Static flow steps showing the debugging process: "Check logs → Identify stuck node → Examine state → Trace decision → Fix prompt/logic → Verify"
- [x] **Callout box** — "The most powerful debugging tool for LangGraph is the state. At any point, you can inspect `plan`, `past_steps`, and `response` to understand exactly what the agent is thinking. Most bugs become obvious when you look at the state at the moment of failure."
- [x] **Quiz** — 2 additional questions (beyond the 3 scenario questions): "Which component would you suspect first if the diagnosis report contains correct data but bad formatting?" and "The app returns an empty response instead of an error. Where do you start looking?"
- [ ] **Group chat animation** — NOT here (used in Module 3)
- [ ] **Data flow animation** — NOT here (used in Module 1 and 3)

## Reference Files to Read
- `references/interactive-elements.md` → "Scenario Quiz", "Code ↔ English Translation Blocks", "Flow Diagrams", "Callout Boxes", "Multiple-Choice Quizzes", "Glossary Tooltips", "Icon-Label Rows"
- `references/content-philosophy.md` → ALL
- `references/gotchas.md` → ALL

## Connections
- **Previous module:** Module 5 "The Safety Nets" — showed the guardrails. This module shows what happens when guardrails aren't enough.
- **Next module:** None (final module) — should end with a wrap-up screen summarizing the key takeaways from the entire course
- **Tone/style notes:** Teal accent. This module should feel empowering — the learner should walk away feeling like they COULD actually debug this system if something broke. End with a "You made it!" wrap-up. Module bg: var(--color-bg-warm) (odd module).
