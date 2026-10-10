"""5 类故障场景的仿真数据与标准根因。

数据供 mock MCP 服务器（bench/mock_servers.py）与假 Prometheus
（bench/fake_prometheus.py）按需读取；场景由 active_scenario.json 切换，
由基准脚本（bench/run_benchmark.py）在每轮运行前写入。
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ACTIVE_SCENARIO_FILE = Path(__file__).parent / "active_scenario.json"

DEFAULT_SCENARIO = "cpu_high"


def set_active_scenario(name: str) -> None:
    ACTIVE_SCENARIO_FILE.write_text(
        json.dumps({"scenario": name}, ensure_ascii=False), encoding="utf-8"
    )


def get_active_scenario() -> str:
    try:
        data = json.loads(ACTIVE_SCENARIO_FILE.read_text(encoding="utf-8"))
        name = str(data.get("scenario", DEFAULT_SCENARIO))
    except Exception:
        name = DEFAULT_SCENARIO
    return name if name in SCENARIOS else DEFAULT_SCENARIO


def rfc3339_utc(minutes_ago: int) -> str:
    """当前 UTC 时间向前推 minutes_ago 分钟，格式 RFC3339（Prometheus activeAt）。"""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


# 每个场景的数据结构：
#   input          发给 Agent 的用户输入
#   alert          假 Prometheus 返回的唯一活跃告警
#   cpu_profile    监控 mock 的 CPU 序列形态: spike | elevated | normal
#   memory_profile 内存序列形态: leak | normal
#   logs           日志列表 [(topic_id, level, message, minutes_ago), ...]
#   ground_truth   标准根因（人工判分依据）
SCENARIOS = {
    "cpu_high": {
        "input": (
            "收到严重告警：data-sync-service 的 CPU 使用率持续 5 分钟超过 80%"
            "（HighCPUUsage）。请诊断根因并给出处理建议。"
        ),
        "alert": {
            "alertname": "HighCPUUsage",
            "severity": "critical",
            "job": "data-sync-service",
            "instance": "10.0.1.23:8080",
            "namespace": "prod",
            "pod": "data-sync-7f9c8-abc12",
            "summary": "CPU 使用率持续超过 80%",
            "description": "实例 10.0.1.23 的 CPU 使用率连续 5 分钟高于 80%，请排查",
            "active_minutes_ago": 25,
        },
        "cpu_profile": "spike",
        "memory_profile": "normal",
        "topic_aliases": {"system-metrics": "topic-001", "application-logs": "topic-002"},
        "logs": [
            ("topic-001", "INFO", "开始执行每日批处理任务：全量对账 (batch_id=B-20260819)", 30),
            ("topic-001", "INFO", "批处理任务进行中：已处理 320000/500000 条记录", 20),
            ("topic-001", "INFO", "正在同步元数据……", 15),
            ("topic-002", "WARN", "批处理任务对账期间线程池打满，任务排队中", 22),
        ],
        "ground_truth": "定时批处理任务集中执行导致 CPU 飙升（任务过载），非内存或磁盘问题",
    },
    "memory_high": {
        "input": (
            "收到严重告警：data-sync-service 的内存使用率持续超过 85%"
            "（HighMemoryUsage）。请诊断根因并给出处理建议。"
        ),
        "alert": {
            "alertname": "HighMemoryUsage",
            "severity": "critical",
            "job": "data-sync-service",
            "instance": "10.0.1.23:8080",
            "namespace": "prod",
            "pod": "data-sync-7f9c8-abc12",
            "summary": "内存使用率持续超过 85%",
            "description": "实例 10.0.1.23 的内存使用率连续 5 分钟高于 85%，请排查",
            "active_minutes_ago": 30,
        },
        "cpu_profile": "normal",
        "memory_profile": "leak",
        "topic_aliases": {"system-metrics": "topic-001", "application-logs": "topic-002"},
        "logs": [
            ("topic-001", "INFO", "正在同步元数据……", 20),
            ("topic-002", "ERROR", "java.lang.OutOfMemoryError: Java heap space", 28),
            ("topic-002", "ERROR", "GC overhead limit exceeded：Full GC 后堆内存未能回收", 12),
        ],
        "ground_truth": "JVM 内存泄漏（OOM、Full GC 无法回收），非 CPU 或流量问题",
    },
    "disk_high": {
        "input": (
            "收到严重告警：api-gateway-service 的磁盘使用率超过 90%"
            "（HighDiskUsage）。请诊断根因并给出处理建议。"
        ),
        "alert": {
            "alertname": "HighDiskUsage",
            "severity": "critical",
            "job": "api-gateway-service",
            "instance": "10.0.2.5:9090",
            "namespace": "prod",
            "pod": "gateway-5c9f7-xk8w2",
            "summary": "磁盘使用率超过 90%",
            "description": "实例 10.0.2.5 的磁盘使用率超过 90%，写入即将失败",
            "active_minutes_ago": 18,
        },
        "cpu_profile": "normal",
        "memory_profile": "normal",
        "topic_aliases": {"application-logs": "topic-003", "system-metrics": "topic-003"},
        "logs": [
            ("topic-003", "ERROR", "java.io.IOException: No space left on device（写入 /var/log/gateway/access.log 失败）", 15),
            ("topic-003", "ERROR", "日志写入失败：磁盘空间不足，丢弃当前批次日志", 5),
            ("topic-003", "WARN", "access.log 大小超过 40GB，日志轮转未生效", 25),
        ],
        "ground_truth": "磁盘空间耗尽（日志文件过大且轮转未生效），非 CPU/内存问题",
    },
    "service_unavailable": {
        "input": (
            "紧急告警：api-gateway-service 健康检查失败，服务不可用"
            "（ServiceUnavailable），用户反馈接口返回 503。请诊断根因并给出处理建议。"
        ),
        "alert": {
            "alertname": "ServiceUnavailable",
            "severity": "critical",
            "job": "api-gateway-service",
            "instance": "10.0.2.5:9090",
            "namespace": "prod",
            "pod": "gateway-5c9f7-xk8w2",
            "summary": "服务健康检查失败",
            "description": "api-gateway-service 健康检查连续 3 次失败，服务不可用",
            "active_minutes_ago": 12,
        },
        "cpu_profile": "normal",
        "memory_profile": "normal",
        "topic_aliases": {"application-logs": "topic-003", "system-events": "topic-003"},
        "logs": [
            ("topic-003", "ERROR", "Connection refused：连接下游数据库 10.0.2.11:3306 失败（连续 30 次）", 10),
            ("topic-003", "ERROR", "HTTP 503 返回给客户端：下游依赖不可用", 8),
            ("topic-003", "INFO", "健康检查 /healthz 返回 503", 6),
        ],
        "ground_truth": "下游数据库连接失败导致服务不可用（依赖故障），非自身 CPU/内存问题",
    },
    "slow_response": {
        "input": (
            "收到警告告警：api-gateway-service 的 P99 响应时间持续 5 分钟超过 3 秒"
            "（SlowResponse），用户反馈页面打开很慢。请诊断根因并给出处理建议。"
        ),
        "alert": {
            "alertname": "SlowResponse",
            "severity": "warning",
            "job": "api-gateway-service",
            "instance": "10.0.2.5:9090",
            "namespace": "prod",
            "pod": "gateway-5c9f7-xk8w2",
            "summary": "P99 响应时间超过 3 秒",
            "description": "api-gateway-service 的 P99 响应时间持续 5 分钟超过 3 秒",
            "active_minutes_ago": 20,
        },
        "cpu_profile": "elevated",
        "memory_profile": "normal",
        "topic_aliases": {"application-logs": "topic-003", "system-metrics": "topic-003"},
        "logs": [
            ("topic-003", "WARN", "调用下游支付服务超时（timeout 5000ms exceeded，累计 120 次）", 15),
            ("topic-003", "WARN", "请求排队等待下游响应，网关线程池占用升高", 10),
        ],
        "ground_truth": "下游支付服务超时导致响应缓慢（依赖性能问题），非自身资源瓶颈",
    },
}
