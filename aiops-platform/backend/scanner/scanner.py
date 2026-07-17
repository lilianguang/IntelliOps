"""多数据源扫描器 - 按技能绑定的数据源类型路由到不同采集逻辑"""

import json
from core.es_client import es_client
from core.db import async_session_factory
from models.skill import Skill
from models.datasource import Datasource
from models.rule import Rule
from rule_engine.loader import rule_loader
from rule_engine.evaluator import rule_evaluator
from rule_engine.executor import action_executor
from sqlalchemy import select


async def scan_skill(skill_id: int):
    """扫描指定技能 - 根据数据源类型路由"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Skill).where(Skill.id == skill_id)
        )
        skill = result.scalar_one_or_none()

    if not skill:
        return

    ds_type = (skill.ds_type or "es").lower()

    try:
        if ds_type == "prometheus":
            await _scan_prometheus(skill)
        else:
            await _scan_es(skill)
    except Exception as e:
        print(f"[扫描器] {skill.skill_name}({ds_type}) 扫描失败: {str(e)}")


async def _scan_es(skill):
    """ES 数据源扫描（原有逻辑）"""
    # 确定索引模式：优先 query_config，回退 index_pattern
    index_pattern = skill.index_pattern
    if skill.query_config and isinstance(skill.query_config, dict):
        index_pattern = skill.query_config.get("index_pattern", index_pattern)

    if not index_pattern:
        print(f"[扫描器] {skill.skill_name}: 未配置ES索引模式，跳过")
        return

    # 构建查询
    es_query = {
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {
                        "gte": f"now-{skill.scan_interval_sec}s",
                        "lte": "now",
                    }}}
                ]
            }
        },
        "sort": [{"@timestamp": "desc"}],
        "size": 200,
    }

    result = await es_client.search(index_pattern, es_query)
    hits = result.get("hits", {}).get("hits", [])
    if not hits:
        return

    logs = [hit["_source"] for hit in hits]
    print(f"[扫描器] {skill.skill_name}(ES): 发现 {len(logs)} 条新日志")

    # 加载规则 + 匹配 + 执行
    rules = await rule_loader.load_rules(skill.id)
    if not rules:
        return

    triggered = []
    for log in logs:
        results = await rule_evaluator.evaluate(log, rules)
        if results:
            actions = await action_executor.execute(results)
            triggered.extend(actions)

    if triggered:
        print(f"[扫描器] {skill.skill_name}(ES): 触发了 {len(triggered)} 个动作")


async def _scan_prometheus(skill):
    """Prometheus 数据源扫描 - 采集指标并交给规则引擎"""
    from core.prometheus_client import get_prometheus_client

    # 获取 Prometheus 客户端配置
    ds_config = await _get_datasource_config(skill.datasource_id)
    client = get_prometheus_client(ds_config)

    # 从 query_config 获取 PromQL 查询列表
    query_config = skill.query_config or {}
    metrics = query_config.get("metrics", [])
    promql_templates = query_config.get("promql_templates", [])

    if not metrics and not promql_templates:
        # 默认采集系统核心指标
        promql_templates = [
            {"name": "cpu_usage", "promql": '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'},
            {"name": "memory_usage", "promql": '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100'},
            {"name": "disk_usage", "promql": '(1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}) * 100'},
            {"name": "load_average", "promql": 'node_load5'},
        ]

    # 执行 PromQL 查询，将结果转换为规则引擎可评估的 dict 格式
    metric_records = []
    for tmpl in promql_templates:
        promql = tmpl if isinstance(tmpl, str) else tmpl.get("promql", "")
        metric_name = tmpl.get("name", promql[:30]) if isinstance(tmpl, dict) else promql[:30]
        if not promql:
            continue
        try:
            data = await client.query(promql)
            results = data.get("result", [])
            for series in results:
                labels = series.get("metric", {})
                value = series.get("value", [None, None])
                if len(value) >= 2 and value[1] != "NaN":
                    record = {
                        "metric_name": metric_name,
                        "metric_value": float(value[1]),
                        "instance": labels.get("instance", ""),
                        "job": labels.get("job", ""),
                        **{k: v for k, v in labels.items() if k not in ("__name__", "instance", "job")},
                    }
                    metric_records.append(record)
        except Exception as e:
            print(f"[扫描器] {skill.skill_name} PromQL查询失败({metric_name}): {str(e)}")

    if not metric_records:
        return

    print(f"[扫描器] {skill.skill_name}(Prometheus): 采集到 {len(metric_records)} 条指标数据")

    # 加载规则 + 匹配 + 执行
    rules = await rule_loader.load_rules(skill.id)
    if not rules:
        return

    triggered = []
    for record in metric_records:
        results = await rule_evaluator.evaluate(record, rules)
        if results:
            actions = await action_executor.execute(results)
            triggered.extend(actions)

    if triggered:
        print(f"[扫描器] {skill.skill_name}(Prometheus): 触发了 {len(triggered)} 个动作")


async def _get_datasource_config(datasource_id: int) -> dict:
    """获取数据源配置"""
    if not datasource_id:
        return {}
    async with async_session_factory() as session:
        result = await session.execute(
            select(Datasource).where(Datasource.id == datasource_id)
        )
        ds = result.scalar_one_or_none()
    if not ds:
        return {}
    return {
        "host": ds.host,
        "port": ds.port,
        "username": ds.username or "",
        "password": ds.password or "",
        "extra_config": ds.extra_config or {},
    }