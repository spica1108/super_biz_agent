"""场景化 mock MCP 服务器（不改动项目内 mcp_servers/ 代码）。

启动方式（项目根目录）：
    .venv/Scripts/python.exe bench/mock_servers.py --role cls      # 127.0.0.1:8103/mcp
    .venv/Scripts/python.exe bench/mock_servers.py --role monitor  # 127.0.0.1:8104/mcp

每个角色只注册自己的工具（避免两个服务器暴露重复工具名）。
每次工具调用读取 bench/active_scenario.json 决定返回哪个场景的数据。
"""

import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastmcp import FastMCP  # noqa: E402

from bench.scenario_data import SCENARIOS, get_active_scenario  # noqa: E402

# 与项目 mock 一致的主题表
TOPICS = [
    {
        "topic_id": "topic-001",
        "topic_name": "数据同步服务日志",
        "service_name": "data-sync-service",
        "region_code": "ap-beijing",
        "create_time": "2024-01-01 10:00:00",
        "description": "数据同步服务的应用日志，包含同步任务执行情况",
    },
    {
        "topic_id": "topic-002",
        "topic_name": "数据同步服务错误日志",
        "service_name": "data-sync-service",
        "region_code": "ap-beijing",
        "create_time": "2024-01-01 10:00:00",
        "description": "数据同步服务的错误日志",
    },
    {
        "topic_id": "topic-003",
        "topic_name": "API网关服务日志",
        "service_name": "api-gateway-service",
        "region_code": "ap-shanghai",
        "create_time": "2024-01-01 10:00:00",
        "description": "API网关服务日志",
    },
]

PORT = {"cls": 8103, "monitor": 8104}

mcp = FastMCP("BenchMock")


def _scenario() -> Dict[str, Any]:
    return SCENARIOS[get_active_scenario()]


def _series(profile: str, base: float, cap: float, step: float, n: int) -> List[float]:
    """按 profile 生成确定性序列（固定种子，可复现）。"""
    random.seed(f"{get_active_scenario()}:{profile}:{n}")
    if profile == "normal":
        return [
            round(max(0.0, min(100.0, base + random.uniform(-3, 3))), 1)
            for _ in range(n)
        ]
    values = []
    for i in range(n):
        v = min(base + i * step, cap) if i >= 2 else base + i * 0.5
        values.append(round(max(0.0, min(100.0, v + random.uniform(-2, 2))), 1))
    return values


def _parse_time(time_str: Optional[str], default_offset_hours: int) -> datetime:
    if time_str:
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.now() + timedelta(hours=default_offset_hours)


def _interval_minutes(interval: str) -> int:
    if interval.endswith("m"):
        return int(interval[:-1])
    if interval.endswith("h"):
        return int(interval[:-1]) * 60
    return 1


def _metric_result(
    service_name: str,
    profile: str,
    base: float,
    cap: float,
    step: float,
    start_dt: datetime,
    end_dt: datetime,
    interval_minutes: int,
    total_gb: Optional[float] = None,
    threshold: float = 80.0,
    label: str = "指标",
) -> Dict[str, Any]:
    n_points = max(1, int((end_dt - start_dt).total_seconds() / 60 / interval_minutes) + 1)
    n_points = min(n_points, 240)  # 限制输出规模
    values = _series(profile, base, cap, step, n_points)

    data_points = []
    for i, v in enumerate(values):
        t = start_dt + timedelta(minutes=i * interval_minutes)
        point: Dict[str, Any] = {"timestamp": t.strftime("%H:%M"), "value": v}
        if total_gb is not None:
            point["used_gb"] = round(v / 100.0 * total_gb, 2)
            point["total_gb"] = total_gb
        data_points.append(point)

    sorted_values = sorted(values)
    p95 = sorted_values[min(int(len(sorted_values) * 0.95), len(sorted_values) - 1)]
    max_value = max(values)
    triggered = max_value > threshold

    return {
        "service_name": service_name,
        "metric_name": label,
        "interval": f"{interval_minutes}m",
        "data_points": data_points,
        "statistics": {
            "avg": round(sum(values) / len(values), 2),
            "max": max_value,
            "min": min(values),
            "p95": round(p95, 2),
            "spike_detected": triggered,
        },
        "alert_info": {
            "triggered": triggered,
            "threshold": threshold,
            "message": f"{label} 超过 {threshold}% 阈值" if triggered else f"{label} 正常",
        },
    }


# ============================================================
# CLS 日志侧工具（镜像 cls_server.py 的工具名与签名）
# ============================================================


def get_current_timestamp() -> int:
    """获取当前时间戳（毫秒）。"""
    return int(datetime.now().timestamp() * 1000)


def get_region_code_by_name(region_name: str) -> Dict[str, Any]:
    """根据地区名称搜索对应的地区代码。"""
    region_mapping = {
        "北京": {"region_code": "ap-beijing", "region_name": "北京", "available": True},
        "上海": {"region_code": "ap-shanghai", "region_name": "上海", "available": True},
        "广州": {"region_code": "ap-guangzhou", "region_name": "广州", "available": True},
    }
    result = region_mapping.get(region_name)
    if result:
        return result
    return {
        "region_code": None,
        "region_name": region_name,
        "available": False,
        "error": f"未找到地区: {region_name}",
    }


def get_topic_info_by_name(topic_name: str, region_code: Optional[str] = None) -> Dict[str, Any]:
    """根据主题名称搜索相关的主题信息。"""
    for topic in TOPICS:
        if topic["topic_name"] == topic_name:
            if region_code is None or topic["region_code"] == region_code:
                return dict(topic)
    return {
        "topic_id": None,
        "topic_name": topic_name,
        "region_code": region_code,
        "error": f"未找到主题: {topic_name}",
    }


def search_topic_by_service_name(
    service_name: str, region_code: Optional[str] = None, fuzzy: bool = True
) -> Dict[str, Any]:
    """根据服务名称搜索相关的日志主题，支持模糊搜索。

    仅返回主题元信息（topic_id 等），不含日志内容。
    需要实际日志内容时，请用返回的 topic_id 调用 search_log。
    """
    print(f"[mock-cls] search_topic_by_service_name({service_name!r})", flush=True)
    matched = []
    for topic in TOPICS:
        if region_code and topic["region_code"] != region_code:
            continue
        if fuzzy:
            if (
                service_name.lower() in topic["service_name"].lower()
                or topic["service_name"].lower() in service_name.lower()
            ):
                matched.append(dict(topic))
        else:
            if topic["service_name"] == service_name:
                matched.append(dict(topic))
    return {
        "total": len(matched),
        "topics": matched,
        "query": {"service_name": service_name, "region_code": region_code, "fuzzy": fuzzy},
        "message": f"找到 {len(matched)} 个匹配的日志主题" if matched else f"未找到服务 '{service_name}' 的日志主题",
    }


def search_log(
    topic_id: Optional[str] = None,
    start_time: Optional[Union[int, str]] = None,
    end_time: Optional[Union[int, str]] = None,
    query: Optional[str] = None,
    limit: int = 100,
    region_code: Optional[str] = None,
) -> Dict[str, Any]:
    """搜索指定日志主题中的日志内容。

    适用场景：排查服务报错、定位异常时间段的日志、按关键字过滤日志。
    这是查询日志正文的唯一工具，需要看日志内容时调用它。

    Args:
        topic_id: 日志主题ID（可选，不传则跨全部主题检索）。
            可先用 search_topic_by_service_name 或 get_topic_info_by_name 获取主题ID
        start_time: 开始时间（可选），格式 "YYYY-MM-DD HH:MM:SS" 或毫秒时间戳
        end_time: 结束时间（可选），格式同上
        query: 查询条件（可选），如 "level:ERROR" 或关键字
        limit: 返回条数上限（默认 100）
        region_code: 地域代码（可选，兼容参数）

    Returns:
        含 total 与 logs 列表的查询结果，每条日志含 timestamp / level / message
    """
    print(f"[mock-cls] search_log(topic_id={topic_id!r}, query={query!r}, region={region_code!r})", flush=True)
    q = (query or "").lower()
    logs: List[Dict[str, Any]] = []
    now = datetime.now()

    # 知识库文档里教的主题名（system-metrics / application-logs 等）
    # 映射到本仿真世界的数据主题，保证按文档查询也能命中证据
    aliases = _scenario().get("topic_aliases", {})
    resolved_topic = aliases.get(topic_id, topic_id) if topic_id else None

    def _level_ok(level: str) -> bool:
        if "error" in q and level != "ERROR":
            return False
        if "warn" in q and level not in ("WARN", "ERROR"):
            return False
        return True

    for tid, level, message, minutes_ago in _scenario()["logs"]:
        if resolved_topic and tid != resolved_topic:
            continue
        if not _level_ok(level):
            continue
        logs.append(
            {
                "timestamp": (now - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S"),
                "level": level,
                "message": message,
            }
        )

    # 查询条件过严导致无结果时，回退到该主题（或全部主题）的场景日志（保证证据可被发现）
    if not logs:
        for tid, level, message, minutes_ago in _scenario()["logs"]:
            if resolved_topic is not None and tid != resolved_topic:
                continue
            logs.append(
                {
                    "timestamp": (now - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S"),
                    "level": level,
                    "message": message,
                }
            )

    # 兜底：当前场景在该主题没有数据时，返回正常 INFO 日志
    known_topics = {t["topic_id"] for t in TOPICS} | set(aliases.keys())
    if not logs and (resolved_topic is None or resolved_topic in known_topics):
        for i in range(min(limit, 5)):
            logs.append(
                {
                    "timestamp": (now - timedelta(minutes=i * 2)).strftime("%Y-%m-%d %H:%M:%S"),
                    "level": "INFO",
                    "message": "正在同步元数据……",
                }
            )

    logs = logs[:limit]
    return {
        "topic_id": topic_id,
        "start_time": start_time,
        "end_time": end_time,
        "query": query,
        "limit": limit,
        "total": len(logs),
        "logs": logs,
        "took_ms": 50,
        "message": f"成功查询 {len(logs)} 条日志" if logs else "未查询到日志",
    }


# ============================================================
# Monitor 监控侧工具（镜像 monitor_server.py 的工具名与签名）
# ============================================================


def query_cpu_metrics(
    service_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    interval: str = "1m",
) -> Dict[str, Any]:
    """查询服务的 CPU 使用率监控数据（按当前活跃场景返回数据）。"""
    print(f"[mock-monitor] query_cpu_metrics({service_name!r})", flush=True)
    profile = _scenario()["cpu_profile"]
    base, cap, step = {"spike": (10.0, 96.0, 8.5), "elevated": (25.0, 58.0, 3.5)}.get(
        profile, (18.0, 100.0, 0.0)
    )
    start_dt = _parse_time(start_time, default_offset_hours=-1)
    end_dt = _parse_time(end_time, default_offset_hours=0)
    return _metric_result(
        service_name,
        profile,
        base,
        cap,
        step,
        start_dt,
        end_dt,
        _interval_minutes(interval),
        threshold=80.0,
        label="cpu_usage_percent",
    )


def query_memory_metrics(
    service_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    interval: str = "1m",
) -> Dict[str, Any]:
    """查询服务的内存使用监控数据（按当前活跃场景返回数据）。"""
    print(f"[mock-monitor] query_memory_metrics({service_name!r})", flush=True)
    profile = _scenario()["memory_profile"]
    base, cap, step = (30.0, 85.0, 5.5) if profile == "leak" else (35.0, 100.0, 0.0)
    start_dt = _parse_time(start_time, default_offset_hours=-1)
    end_dt = _parse_time(end_time, default_offset_hours=0)
    return _metric_result(
        service_name,
        profile,
        base,
        cap,
        step,
        start_dt,
        end_dt,
        _interval_minutes(interval),
        total_gb=8.0,
        threshold=70.0,
        label="memory_usage_percent",
    )


CLS_TOOLS = [
    get_current_timestamp,
    get_region_code_by_name,
    get_topic_info_by_name,
    search_topic_by_service_name,
    search_log,
]

MONITOR_TOOLS = [query_cpu_metrics, query_memory_metrics]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["cls", "monitor"], required=True)
    args = parser.parse_args()

    # 按角色注册工具，避免两个服务器暴露重复工具名
    tools = CLS_TOOLS if args.role == "cls" else MONITOR_TOOLS
    for func in tools:
        mcp.tool()(func)

    print(f"bench mock server ({args.role}, {len(tools)} tools) listening on 127.0.0.1:{PORT[args.role]}/mcp")
    mcp.run(transport="streamable-http", host="127.0.0.1", port=PORT[args.role], path="/mcp")
