"""结构化输出兼容性矩阵测试：找出 DeepSeek 平台可用的组合。

用法：.venv/Scripts/python.exe bench/debug_structured.py
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from pydantic import BaseModel, Field  # noqa: E402


class Tiny(BaseModel):
    steps: list = Field(description="steps")


PROMPT = [("system", "输出一个包含两个元素的 steps 列表"), ("user", "测试")]


async def try_combo(label: str, model: str, method: str, extra_body=None) -> None:
    from langchain_openai import ChatOpenAI

    from app.config import config

    api_key = config.llm_api_key or config.dashscope_api_key
    base_url = config.llm_base_url or "https://api.deepseek.com"
    kwargs = {}
    if extra_body:
        kwargs["extra_body"] = extra_body
    llm = ChatOpenAI(
        model=model, temperature=0, streaming=False,
        base_url=base_url, api_key=api_key, **kwargs,
    )
    chain = llm.with_structured_output(Tiny, method=method)
    try:
        result = await chain.ainvoke(PROMPT)
        print(f"[OK]   {label} -> {result.steps}")
    except Exception as e:
        msg = str(e)
        print(f"[FAIL] {label} -> {type(e).__name__}: {msg[:140]}")


async def main() -> None:
    combos = [
        ("v4-flash  function_calling", "deepseek-v4-flash", "function_calling", None),
        ("v4-pro   function_calling", "deepseek-v4-pro", "function_calling", None),
        ("v4-pro   function_calling + thinking disabled", "deepseek-v4-pro", "function_calling",
         {"thinking": {"type": "disabled"}}),
        ("v4-pro   function_calling + enable_thinking False", "deepseek-v4-pro", "function_calling",
         {"enable_thinking": False}),
        ("v4-pro   default method + thinking disabled", "deepseek-v4-pro", None,
         {"thinking": {"type": "disabled"}}),
        ("v4-flash default method", "deepseek-v4-flash", None, None),
    ]
    for label, model, method, extra in combos:
        await try_combo(label, model, method, extra)


if __name__ == "__main__":
    asyncio.run(main())
