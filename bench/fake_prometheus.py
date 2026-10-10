"""假 Prometheus：127.0.0.1:9091 提供 GET /api/v1/alerts。

返回当前活跃场景（bench/active_scenario.json）对应的告警，
响应格式与 Prometheus Alerts API 一致，供项目内
query_prometheus_alerts 工具（app/tools/query_metrics_alerts.py）直接消费。

启动方式（项目根目录）：
    .venv/Scripts/python.exe bench/fake_prometheus.py
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bench.scenario_data import SCENARIOS, get_active_scenario, rfc3339_utc  # noqa: E402

PORT = 9091


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/api/v1/alerts"):
            alert = SCENARIOS[get_active_scenario()]["alert"]
            body = {
                "status": "success",
                "data": {
                    "alerts": [
                        {
                            "labels": {
                                "alertname": alert["alertname"],
                                "severity": alert["severity"],
                                "instance": alert["instance"],
                                "job": alert["job"],
                                "namespace": alert["namespace"],
                                "pod": alert["pod"],
                            },
                            "annotations": {
                                "summary": alert["summary"],
                                "description": alert["description"],
                            },
                            "state": "firing",
                            "activeAt": rfc3339_utc(alert["active_minutes_ago"]),
                            "value": "1",
                        }
                    ]
                },
            }
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # 静默，不打印请求日志
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"fake prometheus listening on 127.0.0.1:{PORT}")
    server.serve_forever()
