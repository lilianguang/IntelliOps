"""Prometheus 监控分析 API

提供:
- 指标查询（PromQL）
- 系统监控状态采集
- AI 智能分析（流式）
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from api.chat import _enrich_with_cmdb
from core.prometheus_client import PrometheusClient, get_prometheus_client
from core.llm_client import llm_client
from core.db import async_session_factory
from models.datasource import Datasource
from sqlalchemy import select
import json

router = APIRouter()


class PromQueryRequest(BaseModel):
    promql: str
    start: Optional[str] = None
    end: Optional[str] = None
    step: Optional[str] = "60s"
    datasource_id: Optional[int] = None


class PromAnalysisRequest(BaseModel):
    duration_minutes: int = 30
    datasource_id: Optional[int] = None
    custom_queries: Optional[dict] = None  # 用户自定义 PromQL 查询


async def _get_client(datasource_id: Optional[int] = None) -> PrometheusClient:
    """根据数据源ID获取 Prometheus 客户端"""
    if datasource_id:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Datasource).where(Datasource.id == datasource_id, Datasource.ds_type == "prometheus")
            )
            ds = result.scalar_one_or_none()
            if not ds:
                raise HTTPException(status_code=404, detail="Prometheus 数据源不存在")
            config = {
                "host": ds.host, "port": ds.port,
                "username": ds.username, "password": ds.password,
                "extra_config": ds.extra_config or {},
            }
            return get_prometheus_client(config)
    else:
        # 自动选取第一个启用的 Prometheus 数据源
        async with async_session_factory() as session:
            result = await session.execute(
                select(Datasource).where(Datasource.ds_type == "prometheus", Datasource.enabled == 1)
            )
            ds = result.scalar_one_or_none()
            if not ds:
                raise HTTPException(status_code=404, detail="未配置 Prometheus 数据源，请先在配置中心添加")
            config = {
                "host": ds.host, "port": ds.port,
                "username": ds.username, "password": ds.password,
                "extra_config": ds.extra_config or {},
            }
            return get_prometheus_client(config)


@router.post("/prometheus/query")
async def prometheus_query(req: PromQueryRequest):
    """执行 PromQL 查询"""
    client = await _get_client(req.datasource_id)
    try:
        if req.start and req.end:
            data = await client.query_range(req.promql, req.start, req.end, req.step)
        else:
            data = await client.query(req.promql)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@router.get("/prometheus/targets")
async def prometheus_targets(datasource_id: Optional[int] = None):
    """获取采集目标状态"""
    client = await _get_client(datasource_id)
    try:
        targets = await client.get_targets()
        # 汇总
        up = sum(1 for t in targets if t.get("health") == "up")
        down = sum(1 for t in targets if t.get("health") != "up")
        items = [
            {
                "instance": t.get("labels", {}).get("instance", ""),
                "job": t.get("labels", {}).get("job", ""),
                "health": t.get("health", ""),
                "lastScrape": t.get("lastScrape", ""),
                "lastError": (t.get("lastError", "") or "")[:150],
            }
            for t in targets
        ]
        return {"total": len(targets), "up": up, "down": down, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取 targets 失败: {e}")


@router.get("/prometheus/alerts")
async def prometheus_alerts(datasource_id: Optional[int] = None):
    """获取活跃告警"""
    client = await _get_client(datasource_id)
    try:
        alerts = await client.get_alerts()
        items = [
            {
                "alertname": a.get("labels", {}).get("alertname", ""),
                "severity": a.get("labels", {}).get("severity", ""),
                "instance": a.get("labels", {}).get("instance", ""),
                "state": a.get("state", ""),
                "activeAt": a.get("activeAt", ""),
                "summary": (a.get("annotations", {}).get("summary", "")
                            or a.get("annotations", {}).get("description", ""))[:300],
            }
            for a in alerts
        ]
        firing = sum(1 for a in alerts if a.get("state") == "firing")
        return {"total": len(alerts), "firing": firing, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取告警失败: {e}")


@router.post("/prometheus/analyze")
async def prometheus_ai_analysis(req: PromAnalysisRequest):
    """AI 智能分析 Prometheus 监控数据（流式返回）"""
    client = await _get_client(req.datasource_id)

    async def generate():
        try:
            # 1. 采集系统指标
            yield _sse("meta", {"stage": "collecting", "message": "正在采集 Prometheus 监控指标..."})

            metrics = await client.collect_system_metrics(req.duration_minutes)

            # 如果有自定义查询，追加到指标数据
            if req.custom_queries:
                for name, promql in req.custom_queries.items():
                    try:
                        data = await client.query(promql)
                        metrics[f"custom_{name}"] = data.get("result", [])
                    except Exception:
                        metrics[f"custom_{name}"] = {"error": "查询失败"}

            yield _sse("meta", {"stage": "analyzing", "message": "指标采集完成，正在进行 AI 分析..."})

            # 2. 构建 Prompt
            prompt = _build_analysis_prompt(metrics, req.duration_minutes)

            # 2.5 CMDB 资产关联注入
            cmdb_ctx = await _enrich_with_cmdb(prompt)
            if cmdb_ctx:
                prompt += (
                    "\n\n---\n"
                    "## CMDB 资产关联\n"
                    "以下 IP 已在资产库中登记，请用设备名称替代纯 IP，"
                    "按区域/机房维度归纳问题：\n"
                    f"{cmdb_ctx}\n"
                )

            # 3. 流式调用 LLM
            full_text = ""
            async for chunk in llm_client.chat_stream(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4096,
            ):
                full_text += chunk
                yield _sse("content", chunk)

            yield _sse("finish", {"total_chars": len(full_text)})

        except Exception as e:
            yield _sse("error", {"message": f"分析失败: {str(e)}"})

    return StreamingResponse(generate(), media_type="text/event-stream")


def _sse(event: str, data) -> str:
    """构建 SSE 帧"""
    payload = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _build_analysis_prompt(metrics: dict, duration: int) -> str:
    """根据采集结果构建分析 Prompt"""
    def fmt(data):
        if isinstance(data, list) and data:
            # 格式化为易读文本
            lines = []
            for item in data[:15]:
                if isinstance(item, dict):
                    labels = item.get("labels", {})
                    instance = labels.get("instance", "") or labels.get("job", "")
                    if "latest" in item:
                        lines.append(f"  {instance}: 最新={item['latest']}, 最小={item['min']}, 最大={item['max']}, 均值={item['avg']}")
                    else:
                        lines.append(f"  {json.dumps(item, ensure_ascii=False)[:200]}")
            return "\n".join(lines) if lines else "无数据"
        elif isinstance(data, dict) and "error" in data:
            return f"(采集失败: {data['error']})"
        return str(data)[:500] if data else "无数据"

    def fmt_alerts(alerts):
        if not alerts:
            return "无活跃告警"
        lines = []
        for a in alerts[:10]:
            lines.append(f"  [{a.get('severity','?')}] {a.get('alertname','')} - {a.get('instance','')} - {a.get('summary','')}")
        return "\n".join(lines)

    def fmt_targets(targets):
        if not targets:
            return "无数据"
        lines = []
        for t in targets[:15]:
            status = "✓" if t.get("health") == "up" else "✗"
            err = f" ({t['lastError']})" if t.get("lastError") else ""
            lines.append(f"  {status} {t.get('job','')}/{t.get('instance','')}{err}")
        return "\n".join(lines)

    prompt = f"""你是一个资深的 SRE/运维监控专家，请基于以下从 Prometheus 采集的系统监控指标数据进行全面分析。

## 采集时间范围
最近 {duration} 分钟

## 监控指标数据

### CPU 使用率 (%)
{fmt(metrics.get('cpu_usage', []))}

### 内存使用率 (%)
{fmt(metrics.get('memory_usage', []))}

### 磁盘使用率 (%)
{fmt(metrics.get('disk_usage', []))}

### 系统负载 (Load5)
{fmt(metrics.get('load_average', []))}

### 网络流量 (bytes/s)
接收:
{fmt(metrics.get('network_receive', []))}
发送:
{fmt(metrics.get('network_transmit', []))}

### 服务存活状态
{fmt(metrics.get('up_status', []))}

### 活跃告警
{fmt_alerts(metrics.get('active_alerts', []))}

### 采集目标健康状态
{fmt_targets(metrics.get('targets', []))}
"""

    # 追加自定义指标
    custom_keys = [k for k in metrics if k.startswith("custom_")]
    if custom_keys:
        prompt += "\n### 自定义指标\n"
        for k in custom_keys:
            prompt += f"\n**{k.replace('custom_', '')}**:\n{fmt(metrics[k])}\n"

    prompt += """
---

请基于以上数据进行以下分析：

1. **整体健康度评估**：给出当前系统整体健康评分（0-100分），概述关键发现
2. **资源瓶颈分析**：CPU/内存/磁盘/网络是否存在瓶颈或趋势性增长
3. **异常检测**：标识出异常波动的指标、超阈值的实例、不健康的服务
4. **告警分析**：当前活跃告警的严重程度、影响范围和可能原因
5. **容量预警**：是否有资源即将耗尽的风险（如磁盘>80%、内存持续增长等）
6. **运维建议**：针对发现的问题给出具体的处置建议和优先级

请用结构化的中文输出分析报告，重要发现用 **加粗** 标识。"""

    return prompt
