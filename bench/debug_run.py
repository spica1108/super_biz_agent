"""单场景调试运行：异常不吞，完整 traceback 上抛。

用法：.venv/Scripts/python.exe bench/debug_run.py [场景名，默认 cpu_high]
"""

import asyncio
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ["MCP_CLS_URL"] = "http://127.0.0.1:8103/mcp"
os.environ["MCP_MONITOR_URL"] = "http://127.0.0.1:8104/mcp"
os.environ["PROMETHEUS_BASE_URL"] = "http://127.0.0.1:9091"

from bench.scenario_data import SCENARIOS, set_active_scenario  # noqa: E402


async def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "cpu_high"
    set_active_scenario(name)

    from app.services.aiops_service import aiops_service

    scenario = SCENARIOS[name]
    print("scenario:", name, "| input:", scenario["input"][:50])

    initial_state = {
        "input": scenario["input"],
        "plan": [],
        "past_steps": [],
        "response": "",
    }
    config = {"configurable": {"thread_id": f"debug-{name}"}}

    try:
        async for chunk in aiops_service.graph.astream(
            initial_state, config=config, stream_mode="updates"
        ):
            for node, out in chunk.items():
                out = out or {}  # 节点返回空 dict 时 LangGraph 在 updates 模式下产出 None
                if node == "planner":
                    print("PLANNER -> plan steps:", len(out.get("plan", [])))
                elif node == "executor":
                    print("EXECUTOR -> past_steps:", len(out.get("past_steps", [])))
                elif node == "replanner":
                    if out.get("response"):
                        print("REPLANNER -> respond (len", len(out["response"]), ")")
                    elif out.get("plan"):
                        print("REPLANNER -> replan:", out["plan"])
                    else:
                        print("REPLANNER -> continue")
    except Exception:
        traceback.print_exc()
        raise

    final = aiops_service.graph.get_state(config)
    print("FINAL response len:", len((final.values or {}).get("response", "")))


if __name__ == "__main__":
    asyncio.run(main())
