# Module 5: The Safety Nets — Guardrails That Keep AI From Going Off the Rails

## Teaching Arc
- **Metaphor:** Training wheels on a bicycle that auto-deploy when you start wobbling. You don't see them most of the time — but they're always there, ready to catch you. The app has multiple invisible safety nets that prevent the AI from getting stuck in infinite loops, making bad replanning decisions, or drowning in too much conversation history.
- **Opening hook:** AI agents have a dangerous tendency: they can get stuck in loops, endlessly replanning and re-executing without ever reaching a conclusion. Left unchecked, an AI agent would happily burn through your API budget forever. SuperBizAgent has four hard safety limits that force it to eventually give you an answer — even if it's not perfect.
- **Key insight:** The difference between a prototype and production AI is not the AI model — it's the guardrails. Hard limits, forced decision-making, and message trimming are what make an AI agent reliable enough to trust.
- **"Why should I care?":** When you ask AI to build an agent system, you MUST specify safety limits. Otherwise it will build something that works in the demo but breaks in production. Every agent pattern needs an escape hatch.

## Code Snippets (pre-extracted)

**File: app/agent/aiops/replanner.py (lines 128-134)** — MAX_STEPS limit
```python
    # ⚠️ 强制限制：如果已执行步骤过多，直接生成响应
    MAX_STEPS = 8
    if len(past_steps) >= MAX_STEPS:
        logger.warning(f"已执行 {len(past_steps)} 个步骤，超过最大限制 {MAX_STEPS}，强制生成最终响应")
        llm = llm_factory.create_chat_model(temperature=0, streaming=False)
        return await _generate_response(state, llm)
```

**File: app/agent/aiops/replanner.py (lines 198-218)** — Replan guardrails
```python
            elif action == "replan":
                # ⚠️ 强制限制：新步骤数不能超过当前剩余步骤数
                if len(new_steps) > len(plan):
                    logger.warning(
                        f"新步骤数 {len(new_steps)} > 剩余步骤数 {len(plan)}，"
                        f"强制截断为 {len(plan)} 个步骤"
                    )
                    new_steps = new_steps[:len(plan)]
                
                # ⚠️ 二次检查：如果已执行步骤 >= 5，禁止 replan
                if len(past_steps) >= 5:
                    logger.warning(f"已执行 {len(past_steps)} 个步骤，禁止重新规划，强制生成响应")
                    return await _generate_response(state, llm)
```

**File: app/agent/aiops/replanner.py (lines 156-177)** — Replanner prompt (decision priorities)
The system prompt has explicit priority rules: respond > continue > replan. The prompt says: "优先结束 > 保持不变 > 调整计划" and "信息足够就响应，不要追求完美"

**File: app/services/rag_agent_service.py (lines 37-74)** — Message trimming
```python
def trim_messages_middleware(state: AgentState) -> dict[str, Any] | None:
    messages = state["messages"]
    # 如果消息数量较少，无需修剪
    if len(messages) <= 7:
        return None
    # 提取第一条系统消息
    first_msg = messages[0]
    # 保留最近的 6 条消息
    recent_messages = messages[-6:] if len(messages) % 2 == 0 else messages[-7:]
    # 构建新的消息列表
    new_messages = [first_msg] + list(recent_messages)
    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *new_messages]}
```

**File: app/main.py (lines 29-38)** — Graceful degradation
```python
    try:
        milvus_manager.connect()
        logger.info("✅ Milvus 连接成功")
    except Exception as e:
        if not config.allow_missing_external_services:
            raise
        logger.warning(f"Milvus 暂不可用，开发降级模式继续启动: {e}")
```

## Interactive Elements

- [x] **"Spot the Bug" challenge** — Show a version of the Replanner WITHOUT the MAX_STEPS check. The learner clicks the line where the bug is (missing guardrail). Explanation reveals: without this check, the agent could loop forever if the Replanner keeps saying "replan."
- [x] **Code↔English translation** — Two blocks: (1) the MAX_STEPS guard (replanner.py 128-134) — show how 5 lines of code prevent infinite loops, (2) the message trimming middleware — show how it keeps context window from overflowing
- [x] **Quiz** — 3 questions: (1) "Why does the Replanner ban `replan` after 5 steps instead of 3 or 10?" (tradeoff thinking), (2) "The message trimmer keeps the first system message but drops middle messages. Why not just keep the last 6 and drop everything before?" (tests understanding of system prompt importance), (3) Scenario: "You're building a similar agent. What guardrails would you add beyond these four?"
- [x] **Pattern cards** — 4 cards showing each safety net: "MAX_STEPS Limit", "Replan Ban After 5", "Step Count Shrink", "Message Trimming"
- [ ] **Group chat animation** — NOT here (used in Module 3)
- [x] **Callout box** — "Every safety limit is a tradeoff. Too strict → the agent gives up too early with incomplete info. Too loose → the agent burns time and money without getting better results. The numbers 8 and 5 in this codebase were chosen by the developer based on experience — there's no 'correct' answer, only tradeoffs."

## Reference Files to Read
- `references/interactive-elements.md` → "Spot the Bug Challenge", "Code ↔ English Translation Blocks", "Multiple-Choice Quizzes", "Scenario Quiz", "Pattern/Feature Cards", "Callout Boxes", "Glossary Tooltips"
- `references/content-philosophy.md` → ALL
- `references/gotchas.md` → ALL

## Connections
- **Previous module:** Module 4 "The Outside World" — showed the external services that can fail. This module shows the defensive patterns that handle those failures.
- **Next module:** Module 6 "When Things Go Wrong" — real debugging scenarios, applying everything learned
- **Tone/style notes:** Teal accent. The tone should feel like "here's the wisdom the developer earned the hard way." These guardrails look simple but represent real production lessons. Module bg: var(--color-bg) (even module).
