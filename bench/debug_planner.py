"""直接调 Planner 链，绕过项目内 try/except，看真实异常。

用法：.venv/Scripts/python.exe bench/debug_planner.py
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


async def main() -> None:
    from app.agent.aiops.planner import Plan, planner_prompt
    from app.agent.aiops.utils import format_tools_description
    from app.agent.mcp_client import get_mcp_client_with_retry
    from app.core.llm_factory import llm_factory
    from app.tools import DEFAULT_LOCAL_AGENT_TOOLS

    local_tools = list(DEFAULT_LOCAL_AGENT_TOOLS)
    mcp_client = await get_mcp_client_with_retry()
    mcp_tools = await mcp_client.get_tools()
    print("本地工具:", [t.name for t in local_tools])
    print("MCP 工具:", [t.name for t in mcp_tools])

    all_tools = local_tools + mcp_tools
    tools_description = format_tools_description(all_tools)

    llm = llm_factory.create_chat_model(temperature=0, streaming=False)
    chain = planner_prompt | llm.with_structured_output(Plan, method="function_calling")

    try:
        result = await chain.ainvoke(
            {
                "messages": [("user", "测试：诊断 cpu_high 场景")],
                "tools_description": tools_description,
                "experience_context": "",
            }
        )
        print("PLAN:", result)
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
