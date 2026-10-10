"""环境探测：打印非敏感的模型配置 + 验证 LLM/Embedding 连通性。

不打印任何 key 明文；key 仅按项目自身日志风格掩码输出（前8后4）。
用法（项目根目录）：.venv/Scripts/python.exe bench/probe_env.py
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def _mask(key: str) -> str:
    if not key:
        return "<空>"
    if len(key) <= 12:
        return f"<短key len={len(key)}>"
    return f"{key[:8]}...{key[-4:]}"


async def probe_chat() -> str:
    from app.core.llm_factory import llm_factory

    llm = llm_factory.create_chat_model(temperature=0, streaming=False)
    resp = await llm.ainvoke("只回复两个字：OK")
    return resp.content[:50]


def probe_embeddings() -> list:
    """尝试候选 embedding 路径，返回 [(描述, 结果)]。"""
    import httpx
    from openai import OpenAI

    from app.config import config

    results = []
    key = config.embedding_api_key or config.llm_api_key or config.dashscope_api_key
    base = config.embedding_base_url or config.llm_base_url
    model = config.embedding_model or config.dashscope_embedding_model
    endpoint = config.embedding_endpoint_path
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    # 1. 当前 .env 配置（预期 404）
    url = f"{base.rstrip('/')}{endpoint or '/embeddings/multimodal'}"
    try:
        r = httpx.post(url, headers=headers, json={"model": model, "input": [{"type": "text", "text": "test"}], "encoding_format": "float"}, timeout=30)
        results.append((f"当前配置 {url} (model={model})", f"HTTP {r.status_code}"))
    except Exception as e:
        results.append((f"当前配置 {url} (model={model})", f"异常: {e}"))

    # 2. OpenAI 兼容 /embeddings（同 base 同 model）
    try:
        client = OpenAI(api_key=key, base_url=base)
        resp = client.embeddings.create(model=model, input=["test"], encoding_format="float")
        results.append((f"OpenAI格式 {base}/embeddings (model={model})", f"OK dim={len(resp.data[0].embedding)}"))
    except Exception as e:
        results.append((f"OpenAI格式 {base}/embeddings (model={model})", f"异常: {type(e).__name__}"))

    # 3. 若配了 DashScope key，尝试 text-embedding-v4
    if config.dashscope_api_key and config.dashscope_api_key != key:
        try:
            client = OpenAI(
                api_key=config.dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            resp = client.embeddings.create(model="text-embedding-v4", input=["test"], encoding_format="float")
            results.append(("DashScope text-embedding-v4", f"OK dim={len(resp.data[0].embedding)}"))
        except Exception as e:
            results.append(("DashScope text-embedding-v4", f"异常: {type(e).__name__}"))

    return results


async def main() -> None:
    from app.config import config

    print("=== 非敏感配置 ===")
    print(f"llm_provider: {config.llm_provider}")
    print(f"llm_model: {config.llm_model or '<空>'} (rag_model={config.rag_model}, dashscope_model={config.dashscope_model})")
    print(f"llm_base_url: {config.llm_base_url or '<空(默认)>'}")
    print(f"embedding_model: {config.embedding_model or '<空>'}")
    print(f"embedding_base_url: {config.embedding_base_url or '<空(默认)>'}")
    print(f"embedding_endpoint_path: {config.embedding_endpoint_path or '<空>'}")
    print(f"embedding_api_key: {_mask(config.embedding_api_key)}")
    print(f"llm_api_key: {_mask(config.llm_api_key)}")
    print(f"dashscope_api_key: {_mask(config.dashscope_api_key)}")

    print("\n=== LLM 连通性 ===")
    try:
        print("chat 响应:", await probe_chat())
    except Exception as e:
        print("chat 失败:", f"{type(e).__name__}: {str(e)[:200]}")

    print("\n=== Embedding 候选路径 ===")
    for desc, result in probe_embeddings():
        print(f"- {desc} -> {result}")


if __name__ == "__main__":
    asyncio.run(main())
