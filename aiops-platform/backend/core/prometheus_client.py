"""Prometheus 客户端 - 查询 Prometheus 指标数据

支持:
- instant query (当前值)
- range query (时间范围查询)
- 获取告警规则状态
- 获取 targets 健康状态
"""

import httpx
from typing import Optional, List
from datetime import datetime, timedelta


class PrometheusClient:
    """Prometheus HTTP API 客户端"""

    def __init__(self, base_url: str = "", username: str = "", password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

    def _auth(self) -> Optional[tuple]:
        if self.username and self.password:
            return (self.username, self.password)
        return None

    async def _get(self, path: str, params: dict = None) -> dict:
        """发送 GET 请求到 Prometheus API"""
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=15, auth=self._auth()) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    async def query(self, promql: str, time: Optional[str] = None) -> dict:
        """Instant query - 查询当前指标值

        Args:
            promql: PromQL 查询表达式
            time: 可选的时间点 (RFC3339 或 unix timestamp)
        Returns:
            Prometheus API 响应 data 部分
        """
        params = {"query": promql}
        if time:
            params["time"] = time
        result = await self._get("/api/v1/query", params)
        return result.get("data", {})

    async def query_range(
        self, promql: str, start: str, end: str, step: str = "60s"
    ) -> dict:
        """Range query - 查询时间范围内的指标变化

        Args:
            promql: PromQL 查询表达式
            start: 开始时间 (RFC3339 或 unix timestamp)
            end: 结束时间
            step: 采样步长 (如 60s, 5m)
        Returns:
            Prometheus API 响应 data 部分
        """
        params = {"query": promql, "start": start, "end": end, "step": step}
        result = await self._get("/api/v1/query_range", params)
        return result.get("data", {})

    async def get_targets(self) -> List[dict]:
        """获取所有采集目标的状态"""
        result = await self._get("/api/v1/targets")
        targets = result.get("data", {}).get("activeTargets", [])
        return targets

    async def get_alerts(self) -> List[dict]:
        """获取当前活跃的告警"""
        result = await self._get("/api/v1/alerts")
        alerts = result.get("data", {}).get("alerts", [])
        return alerts

    async def get_rules(self) -> List[dict]:
        """获取告警规则"""
        result = await self._get("/api/v1/rules")
        groups = result.get("data", {}).get("groups", [])
        return groups

    async def get_metadata(self, metric: str = "") -> dict:
        """获取指标的元数据"""
        params = {}
        if metric:
            params["metric"] = metric
        result = await self._get("/api/v1/metadata", params)
        return result.get("data", {})

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            async with httpx.AsyncClient(timeout=8, auth=self._auth()) as client:
                resp = await client.get(f"{self.base_url}/-/healthy")
                return resp.status_code == 200
        except Exception:
            return False

    async def collect_system_metrics(self, duration_minutes: int = 30) -> dict:
        """采集系统核心监控指标（用于 AI 分析）

        采集最近 N 分钟的关键指标，返回结构化数据。
        """
        end = datetime.now()
        start = end - timedelta(minutes=duration_minutes)
        start_str = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end.strftime("%Y-%m-%dT%H:%M:%SZ")
        step = "60s" if duration_minutes <= 60 else "300s"

        # 核心 PromQL 查询集
        queries = {
            "cpu_usage": '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
            "memory_usage": '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
            "disk_usage": '(1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}) * 100',
            "network_receive": 'rate(node_network_receive_bytes_total{device!~"lo|veth.*"}[5m])',
            "network_transmit": 'rate(node_network_transmit_bytes_total{device!~"lo|veth.*"}[5m])',
            "load_average": 'node_load5',
            "up_status": "up",
        }

        metrics_data = {}
        for name, promql in queries.items():
            try:
                data = await self.query_range(promql, start_str, end_str, step)
                results = data.get("result", [])
                metrics_data[name] = self._summarize_range_result(results)
            except Exception as e:
                metrics_data[name] = {"error": str(e)}

        # 获取活跃告警
        try:
            alerts = await self.get_alerts()
            metrics_data["active_alerts"] = [
                {
                    "alertname": a.get("labels", {}).get("alertname", ""),
                    "severity": a.get("labels", {}).get("severity", ""),
                    "instance": a.get("labels", {}).get("instance", ""),
                    "state": a.get("state", ""),
                    "summary": (a.get("annotations", {}).get("summary", "")
                                or a.get("annotations", {}).get("description", ""))[:200],
                }
                for a in alerts[:20]
            ]
        except Exception:
            metrics_data["active_alerts"] = []

        # 获取 target 状态
        try:
            targets = await self.get_targets()
            metrics_data["targets"] = [
                {
                    "instance": t.get("labels", {}).get("instance", ""),
                    "job": t.get("labels", {}).get("job", ""),
                    "health": t.get("health", ""),
                    "lastError": (t.get("lastError", "") or "")[:100],
                }
                for t in targets[:30]
            ]
        except Exception:
            metrics_data["targets"] = []

        return metrics_data

    def _summarize_range_result(self, results: list) -> list:
        """摘要 range query 结果：取每个 series 的 latest/min/max/avg"""
        summary = []
        for series in results[:20]:  # 限制最多20个 series
            metric = series.get("metric", {})
            values = series.get("values", [])
            if not values:
                continue
            nums = [float(v[1]) for v in values if v[1] != "NaN"]
            if not nums:
                continue
            summary.append({
                "labels": metric,
                "latest": round(nums[-1], 2),
                "min": round(min(nums), 2),
                "max": round(max(nums), 2),
                "avg": round(sum(nums) / len(nums), 2),
                "samples": len(nums),
            })
        return summary


# 全局单例（延迟初始化，由数据源配置驱动）
prometheus_client: Optional[PrometheusClient] = None


def get_prometheus_client(config: dict = None) -> PrometheusClient:
    """获取 Prometheus 客户端实例"""
    global prometheus_client
    if config:
        base_url = config.get("base_url") or config.get("url") or ""
        if not base_url:
            host = config.get("host", "localhost")
            port = config.get("port", 9090)
            use_ssl = config.get("extra_config", {}).get("use_ssl", False)
            scheme = "https" if use_ssl else "http"
            base_url = f"{scheme}://{host}:{port}"
        prometheus_client = PrometheusClient(
            base_url=base_url,
            username=config.get("username", ""),
            password=config.get("password", ""),
        )
    if prometheus_client is None:
        prometheus_client = PrometheusClient(base_url="http://localhost:9090")
    return prometheus_client
