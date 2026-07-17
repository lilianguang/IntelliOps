"""仪表盘数据 API"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from core.db import async_session_factory
from models.event import Event, EventStatus
from models.keyword import RiskLevel
from models.rule import Rule, RuleType
from sqlalchemy import select, func, case, text

router = APIRouter()

# 中国标准时间 UTC+8
CST = timezone(timedelta(hours=8))


def to_cst(dt) -> str:
    """将 UTC datetime 转为中国标准时间 (UTC+8) 字符串"""
    if dt is None:
        return ''
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CST).strftime('%Y-%m-%d %H:%M:%S')


@router.get("/dashboard/stats")
async def get_dashboard_stats():
    """获取仪表盘统计数据"""
    async with async_session_factory() as session:
        # 总异常事件
        total = await session.execute(select(func.count(Event.id)))
        total_count = total.scalar() or 0

        # 高危事件
        high_risk = await session.execute(
            select(func.count(Event.id))
            .where(Event.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]))
        )
        high_count = high_risk.scalar() or 0

        # 今日告警数
        today_alert = await session.execute(
            select(func.count(Event.id))
            .where(func.DATE(Event.created_at) == func.CURDATE())
        )
        today_count = today_alert.scalar() or 0

        # 处理中
        processing = await session.execute(
            select(func.count(Event.id))
            .where(Event.status == EventStatus.NEW)
        )
        processing_count = processing.scalar() or 0

        return {
            "total_events": total_count,
            "high_risk_events": high_count,
            "today_alerts": today_count,
            "processing": processing_count,
        }


@router.get("/dashboard/recent-events")
async def get_recent_events(limit: int = 10):
    """获取最近事件"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Event)
            .order_by(Event.last_seen.desc())
            .limit(limit)
        )
        events = result.scalars().all()
        return {
            "items": [
                {
                    "event_id": e.event_id,
                    "summary": e.summary,
                    "risk_level": e.risk_level.value if hasattr(e.risk_level, 'value') else e.risk_level,
                    "source_device": e.source_device,
                    "occurrence_count": e.occurrence_count or 1,
                    "first_seen": to_cst(e.first_seen),
                    "last_seen": to_cst(e.last_seen),
                }
                for e in events
            ]
        }


@router.get("/dashboard/alert-trend")
async def get_alert_trend(
    days: int = 7,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    granularity: str = "day",
):
    """获取告警趋势历史数据，支持按天或按小时聚合，含按事件类型分组。"""
    is_hourly = granularity == "hour"

    # 解析日期区间
    fmt = "%Y-%m-%d"
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, fmt)
        except ValueError:
            raise HTTPException(status_code=400, detail="end_date 格式应为 YYYY-MM-DD")
    else:
        end_dt = datetime.now(CST).replace(hour=23, minute=59, second=59)

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, fmt)
        except ValueError:
            raise HTTPException(status_code=400, detail="start_date 格式应为 YYYY-MM-DD")
    else:
        start_dt = end_dt - timedelta(days=max(days - 1, 0))

    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    start_str = start_dt.strftime(fmt)
    end_str = end_dt.strftime(fmt)

    async with async_session_factory() as session:
        high_expr = case(
            (Event.risk_level.in_(["high", "critical"]), 1), else_=0
        )

        if is_hourly:
            hour_expr = func.DATE_FORMAT(Event.last_seen, '%Y-%m-%d %H:00')
            result = await session.execute(
                select(
                    hour_expr.label("time_key"),
                    Event.event_type,
                    func.count(Event.id).label("count"),
                    func.sum(high_expr).label("high_count"),
                )
                .where(Event.last_seen >= start_dt)
                .where(Event.last_seen <= end_dt + timedelta(days=1))
                .group_by(hour_expr, Event.event_type)
                .order_by(hour_expr)
            )
        else:
            day_expr = func.DATE(Event.last_seen)
            result = await session.execute(
                select(
                    day_expr.label("time_key"),
                    Event.event_type,
                    func.count(Event.id).label("count"),
                    func.sum(high_expr).label("high_count"),
                )
                .where(day_expr.between(start_str, end_str))
                .group_by(day_expr, Event.event_type)
                .order_by(day_expr)
            )

        rows = result.all()

        # 按时间点聚合，含按类型分组
        from collections import defaultdict
        time_data = defaultdict(lambda: {"count": 0, "high_count": 0, "by_type": defaultdict(int)})
        for r in rows:
            key = str(r.time_key)
            time_data[key]["count"] += int(r.count or 0)
            time_data[key]["high_count"] += int(r.high_count or 0)
            time_data[key]["by_type"][r.event_type] += int(r.count or 0)

    # 补全缺失时间点，保证前端图表连续
    items = []
    if is_hourly:
        cur = start_dt.replace(hour=0, minute=0, second=0)
        end_full = end_dt.replace(hour=23, minute=0, second=0)
        while cur <= end_full:
            key = cur.strftime('%Y-%m-%d %H:00')
            info = time_data.get(key, {"count": 0, "high_count": 0, "by_type": {}})
            items.append({
                "date": key,
                "count": info["count"],
                "high_count": info["high_count"],
                "by_type": dict(info.get("by_type", {})),
            })
            cur += timedelta(hours=1)
    else:
        cur = start_dt
        while cur <= end_dt:
            key = cur.strftime(fmt)
            info = time_data.get(key, {"count": 0, "high_count": 0, "by_type": {}})
            items.append({
                "date": key,
                "count": info["count"],
                "high_count": info["high_count"],
                "by_type": dict(info.get("by_type", {})),
            })
            cur += timedelta(days=1)

    total = sum(i["count"] for i in items)
    return {
        "start_date": start_str,
        "end_date": end_str,
        "granularity": granularity,
        "total": total,
        "items": items,
    }


@router.get("/dashboard/operation-metrics")
async def get_operation_metrics():
    """AI 运营中心核心运营指标

    - 近24h异常事件数及较前24h变化
    - 待处理事件总数及较昨日变化
    - 已恢复事件总数（近24h）及较前24h变化
    - AI 综合评分：预留字段
    """
    now = datetime.now(CST)
    last_7d = now - timedelta(days=7)

    async with async_session_factory() as session:
        # 异常事件总数（全量）
        total_abnormal = await session.execute(
            select(func.count(Event.id))
        )
        total_abnormal_count = total_abnormal.scalar() or 0

        # 近7天异常事件（用于参考）
        recent_7d = await session.execute(
            select(func.count(Event.id))
            .where(Event.created_at >= last_7d)
        )
        recent_7d_count = recent_7d.scalar() or 0

        # 待处理事件总数
        pending = await session.execute(
            select(func.count(Event.id))
            .where(Event.status == EventStatus.NEW)
        )
        pending_count = pending.scalar() or 0

        # 已恢复事件总数
        auto_recovered = await session.execute(
            select(func.count(Event.id))
            .where(Event.status == EventStatus.RESOLVED)
        )
        auto_recovered_count = auto_recovered.scalar() or 0

        # 高危事件总数
        high_total = await session.execute(
            select(func.count(Event.id))
            .where(Event.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]))
        )
        high_total_count = high_total.scalar() or 0

        # === 7 天趋势数据 ===
        trend_7d_start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        trend_result = await session.execute(
            select(
                func.DATE(Event.created_at).label('dt'),
                func.count(Event.id).label('cnt'),
            )
            .where(Event.created_at >= trend_7d_start)
            .group_by(func.DATE(Event.created_at))
        )
        trend_map = {str(r.dt): int(r.cnt) for r in trend_result.all()}

        # 按状态分组的趋势
        status_trend_result = await session.execute(
            select(
                func.DATE(Event.created_at).label('dt'),
                Event.status,
                func.count(Event.id).label('cnt'),
            )
            .where(Event.created_at >= trend_7d_start)
            .group_by(func.DATE(Event.created_at), Event.status)
        )
        status_trend_map = {}
        for r in status_trend_result.all():
            dt_str = str(r.dt)
            st = r.status.value if hasattr(r.status, 'value') else str(r.status)
            status_trend_map.setdefault(dt_str, {})[st] = int(r.cnt)

        # 生成7天日期序列
        abnormal_trend = []
        pending_trend = []
        recovered_trend = []
        for i in range(7):
            day = trend_7d_start + timedelta(days=i)
            # 转为 CST 日期字符串
            if day.tzinfo:
                day_cst = day.astimezone(CST)
            else:
                day_cst = day
            day_str = day_cst.strftime('%Y-%m-%d')
            abnormal_trend.append(trend_map.get(day_str, 0))
            day_status = status_trend_map.get(day_str, {})
            pending_trend.append(day_status.get('new', 0))
            recovered_trend.append(day_status.get('resolved', 0))

    return {
        "ai_score": None,
        "ai_score_trend": [],
        "today_abnormal_events": total_abnormal_count,
        "today_abnormal_events_delta": recent_7d_count,
        "abnormal_trend": abnormal_trend,
        "pending_events": pending_count,
        "pending_events_delta": high_total_count,
        "pending_trend": pending_trend,
        "auto_recovered_events": auto_recovered_count,
        "auto_recovered_events_delta": 0,
        "recovered_trend": recovered_trend,
    }


@router.get("/dashboard/risk-heatmap")
async def get_risk_heatmap():
    """风险热力图：按领域和风险等级统计近30天事件"""
    now = datetime.now(CST)
    last_30d = now - timedelta(days=30)

    DOMAIN_MAP = {
        'dangerous_command': '网络',
        'command_monitor': '网络',
        'severity_filter': '网络',
        'http_status_alert': '应用',
        'response_time_alert': '应用',
        'keyword_match': '存储',
        'metric_threshold': '基础设施',
        'ai_inspection': 'AI巡检',
    }

    async with async_session_factory() as session:
        result = await session.execute(
            select(
                Event.event_type,
                Event.risk_level,
                func.count(Event.id).label('cnt'),
            )
            .where(Event.created_at >= last_30d)
            .group_by(Event.event_type, Event.risk_level)
        )
        rows = result.all()

    domain_data = {}
    for r in rows:
        et = r.event_type
        domain = DOMAIN_MAP.get(et, '其他')
        risk = r.risk_level.value if hasattr(r.risk_level, 'value') else str(r.risk_level)
        if domain not in domain_data:
            domain_data[domain] = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        domain_data[domain][risk] = domain_data[domain].get(risk, 0) + int(r.cnt or 0)

    heatmap = []
    for domain, risks in domain_data.items():
        total = sum(risks.values())
        heatmap.append({
            'domain': domain,
            'total': total,
            'critical': risks.get('critical', 0),
            'high': risks.get('high', 0),
            'medium': risks.get('medium', 0),
            'low': risks.get('low', 0),
        })

    heatmap.sort(key=lambda x: x['total'], reverse=True)
    return {'items': heatmap}


@router.get("/reports/daily-summary")
async def get_daily_summary():
    """今日 AI 报告摘要

    结合规则配置与事件数据，生成精简运维报告，重点体现问题。
    覆盖：网络监控、危险命令、日志级别、配置变更、业务状态码、响应时间、存储关键字等。
    """
    now = datetime.now(CST)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    EVENT_TYPE_LABELS = {
        "dangerous_command": "危险命令",
        "command_monitor": "命令监控",
        "severity_filter": "日志级别告警",
        "http_status_alert": "HTTP状态告警",
        "response_time_alert": "响应时间告警",
        "keyword_match": "关键字匹配",
        "metric_threshold": "指标阈值告警",
        "ai_analysis_trigger": "AI分析触发",
        "ignore_rule": "忽略规则",
        "ai_inspection": "AI巡检",
    }

    async with async_session_factory() as session:
        # 1. 近24h事件按类型统计
        result_types = await session.execute(
            select(Event.event_type, func.count(Event.id))
            .where(Event.created_at >= now - timedelta(hours=24))
            .group_by(Event.event_type)
            .order_by(func.count(Event.id).desc())
        )
        categories = [
            {"name": EVENT_TYPE_LABELS.get(row[0], row[0] or "其他"), "key": row[0] or "other", "count": row[1]}
            for row in result_types.all()
        ]
        total = sum(c["count"] for c in categories)

        # 2. 近24h风险等级分布
        result_risk = await session.execute(
            select(
                Event.risk_level,
                func.count(Event.id),
            )
            .where(Event.created_at >= now - timedelta(hours=24))
            .group_by(Event.risk_level)
        )
        risk_dist = {}
        for row in result_risk.all():
            lv = row[0].value if hasattr(row[0], 'value') else str(row[0])
            risk_dist[lv] = row[1]

        # 3. 最近10条高危事件
        high_events_result = await session.execute(
            select(Event.event_id, Event.event_type, Event.risk_level, Event.summary, Event.last_seen)
            .where(Event.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]))
            .order_by(Event.last_seen.desc())
            .limit(10)
        )
        high_events = [
            {
                "event_id": e.event_id,
                "type": EVENT_TYPE_LABELS.get(e.event_type, e.event_type),
                "risk": e.risk_level.value if hasattr(e.risk_level, 'value') else str(e.risk_level),
                "summary": e.summary or '',
                "last_seen": to_cst(e.last_seen),
            }
            for e in high_events_result.all()
        ]

        # 4. 启用规则统计
        rules_result = await session.execute(
            select(Rule.rule_type, func.count(Rule.id))
            .where(Rule.enabled == 1)
            .group_by(Rule.rule_type)
        )
        rules_stats = [
            {"type": EVENT_TYPE_LABELS.get(r.rule_type.value if hasattr(r.rule_type, 'value') else str(r.rule_type), str(r.rule_type)), "count": r[1]}
            for r in rules_result.all()
        ]
        total_rules = sum(r["count"] for r in rules_stats)

        # 5. 待处理事件总数
        pending_result = await session.execute(
            select(func.count(Event.id)).where(Event.status == EventStatus.NEW)
        )
        pending_count = pending_result.scalar() or 0

    # 生成精简报告
    if total == 0:
        summary_parts = [f"近24小时无新增异常事件，系统运行平稳。当前已启用 {total_rules} 条监控规则。"]
        if pending_count > 0:
            summary_parts.append(f"待处理事件 {pending_count} 起，请及时关注。")
        summary = " ".join(summary_parts)
    else:
        top_type = categories[0]
        summary_parts = [f"近24小时共 {total} 起异常事件，其中{top_type['name']}最多（{top_type['count']} 起）。"]
        critical = risk_dist.get("critical", 0)
        high = risk_dist.get("high", 0)
        if critical + high > 0:
            summary_parts.append(f"高危/严重事件 {critical + high} 起，需重点关注。")
        if pending_count > 0:
            summary_parts.append(f"待处理事件 {pending_count} 起。")
        summary = " ".join(summary_parts)

    return {
        "summary": summary,
        "total": total,
        "categories": categories,
        "risk_distribution": risk_dist,
        "high_risk_events": high_events,
        "rules_stats": rules_stats,
        "pending_count": pending_count,
    }