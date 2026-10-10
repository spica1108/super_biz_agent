"""AIOps Plan-Execute-Replan 场景化基准。

测量指标（自动记录）：
- 计划步骤数、实际执行步数、replan 触发次数、三态决策序列
- 8 步硬上限强制结束、≥5 步禁止 replan 是否触发
- 知识库检索是否命中、每轮端到端耗时
- 根因命中率需人工判分：对照各场景 ground_truth 阅读报告

基线：同一 LLM 不检索、不调工具直接回答，对比根因命中率。

前置条件（项目根目录）：
1. Milvus 已启动且 aiops-docs 已入库（知识库检索）
2. mock MCP 服务器已启动：
     .venv/Scripts/python.exe bench/mock_servers.py --role cls
     .venv/Scripts/python.exe bench/mock_servers.py --role monitor
3. 假 Prometheus 已启动：
     .venv/Scripts/python.exe bench/fake_prometheus.py

运行：.venv/Scripts/python.exe bench/run_benchmark.py

输出：bench/results/results.json + 每轮报告 .md
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# 必须在 import app.* 之前设置（pydantic-settings：环境变量优先于 .env）
os.environ["MCP_CLS_URL"] = "http://127.0.0.1:8103/mcp"
os.environ["MCP_MONITOR_URL"] = "http://127.0.0.1:8104/mcp"
os.environ["PROMETHEUS_BASE_URL"] = "http://127.0.0.1:9091"

from loguru import logger  # noqa: E402

from bench.scenario_data import SCENARIOS, set_active_scenario  # noqa: E402

RUNS_PER_SCENARIO = 2
RESULTS_DIR = Path(__file__).parent / "results"

_log_buffer: list = []


async def run_agent_scenario(name: str, run_index: int) -> dict:
    """跑一次完整 Plan-Execute-Replan 诊断，返回结构化指标。"""
    from app.services.aiops_service import aiops_service

    set_active_scenario(name)
    scenario = SCENARIOS[name]

    start_idx = len(_log_buffer)
    sink_id = logger.add(lambda msg: _log_buffer.append(str(msg)), level="INFO")
    start = time.perf_counter()
    try:
        initial_state = {
            "input": scenario["input"],
            "plan": [],
            "past_steps": [],
            "response": "",
        }
        config = {"configurable": {"thread_id": f"{name}-{run_index}"}}

        plan_steps = 0
        executed = 0
        decisions = []
        async for chunk in aiops_service.graph.astream(
            initial_state, config=config, stream_mode="updates"
        ):
            for node_name, output in chunk.items():
                output = output or {}  # 节点返回空 dict 时 LangGraph 在 updates 模式下产出 None
                if node_name == "planner":
                    plan_steps = len(output.get("plan", []))
                elif node_name == "executor":
                    executed += 1
                elif node_name == "replanner":
                    if output.get("response"):
                        decisions.append("respond")
                    elif output.get("plan"):
                        decisions.append("replan")
                    else:
                        decisions.append("continue")

        final = aiops_service.graph.get_state(config)
        response = (final.values or {}).get("response", "")
        error = ""
    except Exception as e:
        response = ""
        error = f"{type(e).__name__}: {e}"
    finally:
        logger.remove(sink_id)

    duration = time.perf_counter() - start
    log_text = "\n".join(_log_buffer[start_idx:])

    return {
        "scenario": name,
        "run": run_index,
        "plan_steps": plan_steps,
        "executed_steps": executed,
        "replanner_decisions": decisions,
        "replan_count": decisions.count("replan"),
        "forced_respond_8steps": "强制生成最终响应" in log_text,
        "replan_blocked_5steps": "禁止重新规划" in log_text,
        "knowledge_retrieved": "找到相关经验文档" in log_text,
        "duration_s": round(duration, 1),
        "error": error,
        "response": response,
    }


async def run_baseline(name: str) -> dict:
    """基线：同一 LLM 不检索、不调工具，直接回答。"""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.core.llm_factory import llm_factory

    scenario = SCENARIOS[name]
    llm = llm_factory.create_chat_model(temperature=0, streaming=False)
    messages = [
        SystemMessage(
            content="你是一名资深运维专家。请直接给出最可能的根因结论和处理建议，"
            "不要提问，不要调用任何工具。"
        ),
        HumanMessage(content=scenario["input"]),
    ]
    resp = await llm.ainvoke(messages)
    return {
        "scenario": name,
        "run": "baseline",
        "response": resp.content if hasattr(resp, "content") else str(resp),
    }


async def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    results = []

    # 可选：只跑指定场景（python bench/run_benchmark.py service_unavailable）
    targets = sys.argv[1:] if len(sys.argv) > 1 else list(SCENARIOS.keys())
    scenarios = {name: SCENARIOS[name] for name in targets if name in SCENARIOS}

    for name, scenario in scenarios.items():
        print(f"\n=== 场景 {name}（标准根因：{scenario['ground_truth'][:40]}…） ===")
        for i in range(RUNS_PER_SCENARIO):
            r = await run_agent_scenario(name, i)
            results.append(r)
            report_path = RESULTS_DIR / f"{name}-run{i}.md"
            report_path.write_text(r["response"], encoding="utf-8")
            print(
                f"  run{i}: 计划{str(r['plan_steps']).ljust(2)}步 执行{r['executed_steps']}步 "
                f"replan×{r['replan_count']} 决策{r['replanner_decisions']} "
                f"8步强制={r['forced_respond_8steps']} RAG命中={r['knowledge_retrieved']} "
                f"{r['duration_s']}s" + (f" 错误: {r['error']}" if r["error"] else "")
            )
        b = await run_baseline(name)
        results.append(b)
        (RESULTS_DIR / f"{name}-baseline.md").write_text(b["response"], encoding="utf-8")
        print(f"  baseline: 已保存 {name}-baseline.md")

    (RESULTS_DIR / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n结果已写入 bench/results/（results.json + 各轮报告 .md）")
    print("根因命中率需人工判分：对照 aiops-docs 与各场景 ground_truth 阅读报告。")


if __name__ == "__main__":
    asyncio.run(main())
