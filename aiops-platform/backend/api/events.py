"""事件中心 API"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import orjson
from core.db import async_session_factory
from core.llm_client import llm_client
from core.request_context import get_request_id
from gateway.model_scheduler import model_scheduler
from models.event import Event, EventStatus, AlertLog
from api.dashboard import to_cst
from sqlalchemy import select, func

router = APIRouter()


class StatusBody(BaseModel):
    status: str


class BatchStatusBody(BaseModel):
    event_ids: List[str]
    status: str


def _serialize_event(e: Event, ip_to_name: dict = None) -> dict:
    """序列化事件对象，时间戳转为 UTC+8"""
    # 如果 source_device 是 IP，尝试从 CMDB 映射转为设备名
    device_display = e.source_device
    if ip_to_name and device_display and device_display in ip_to_name:
        device_display = ip_to_name[device_display]
    return {
        "id": e.id,
        "event_id": e.event_id,
        "skill_id": e.skill_id,
        "event_type": e.event_type,
        "risk_level": e.risk_level.value if hasattr(e.risk_level, 'value') else str(e.risk_level),
        "summary": e.summary,
        "source_device": device_display,
        "source_ip": e.source_ip,
        "status": e.status.value if hasattr(e.status, 'value') else str(e.status),
        "occurrence_count": e.occurrence_count,
        "raw_log": e.raw_log,
        "ai_report": e.ai_report,
        "first_seen": to_cst(e.first_seen),
        "last_seen": to_cst(e.last_seen),
        "created_at": to_cst(e.created_at),
    }


@router.get("/events")
async def list_events(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
    skill_id: Optional[int] = None,
    source_device: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
):
    """事件列表（支持分页/筛选/时间范围）

    start_time / end_time 格式：YYYY-MM-DD HH:MM:SS 或 ISO 8601
    """
    from datetime import datetime
    from models.cmdb import CMDBAsset

    async with async_session_factory() as session:
        # 构建 CMDB IP→name 映射（用于显示设备名）
        cmdb_result = await session.execute(
            select(CMDBAsset.ip_address, CMDBAsset.name)
            .where(CMDBAsset.ip_address != "")
        )
        ip_to_name = {row[0]: row[1] for row in cmdb_result.all() if row[0] and row[1]}
        # 反向映射：name→IP 列表（用于按设备名筛选时匹配历史 IP 事件）
        name_to_ips = {}
        for ip, name in ip_to_name.items():
            name_to_ips.setdefault(name, []).append(ip)

        query = select(Event)

        if status:
            query = query.where(Event.status == status)
        if risk_level:
            query = query.where(Event.risk_level == risk_level)
        if skill_id:
            query = query.where(Event.skill_id == skill_id)
        if source_device:
            # 如果筛选的是 CMDB 设备名，同时匹配历史 IP
            ips = name_to_ips.get(source_device, [])
            if ips:
                from sqlalchemy import or_
                query = query.where(
                    or_(Event.source_device == source_device, Event.source_device.in_(ips))
                )
            else:
                query = query.where(Event.source_device == source_device)

        # 时间范围筛选
        def parse_dt(s):
            if not s:
                return None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(s, fmt)
                except ValueError:
                    continue
            return None

        st = parse_dt(start_time)
        et = parse_dt(end_time)
        if st:
            query = query.where(Event.last_seen >= st)
        if et:
            query = query.where(Event.last_seen <= et)

        # 总条数
        count_q = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_q)).scalar()

        # 分页
        query = query.order_by(Event.last_seen.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(query)
        events = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_serialize_event(e, ip_to_name) for e in events],
        }


@router.get("/events/stats")
async def get_event_stats(days: int = 7):
    """事件统计面板

    返回总览、按风险等级、状态、事件类型、设备的分布，以及最近 N 天趋势。
    """
    from datetime import datetime, timedelta
    from api.dashboard import CST

    now = datetime.now(CST)
    start_dt = now - timedelta(days=max(days - 1, 0))
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = now.strftime("%Y-%m-%d")

    async with async_session_factory() as session:
        # 总数
        total = await session.execute(select(func.count(Event.id)))
        total_count = total.scalar() or 0

        # 按风险等级
        risk_result = await session.execute(
            select(Event.risk_level, func.count(Event.id))
            .group_by(Event.risk_level)
        )
        by_risk = {
            (row[0].value if hasattr(row[0], "value") else str(row[0])): row[1]
            for row in risk_result.all()
        }

        # 按状态
        status_result = await session.execute(
            select(Event.status, func.count(Event.id))
            .group_by(Event.status)
        )
        by_status = {
            (row[0].value if hasattr(row[0], "value") else str(row[0])): row[1]
            for row in status_result.all()
        }

        # 按事件类型 Top 10
        type_result = await session.execute(
            select(Event.event_type, func.count(Event.id))
            .group_by(Event.event_type)
            .order_by(func.count(Event.id).desc())
            .limit(10)
        )
        by_type = [{"name": row[0] or "其他", "count": row[1]} for row in type_result.all()]

        # 按设备 Top 10
        device_result = await session.execute(
            select(Event.source_device, func.count(Event.id))
            .where(Event.source_device != "")
            .where(Event.source_device.isnot(None))
            .group_by(Event.source_device)
            .order_by(func.count(Event.id).desc())
            .limit(10)
        )
        by_device = [{"name": row[0] or "未知", "count": row[1]} for row in device_result.all()]

        # 最近 N 天趋势
        day_expr = func.DATE(Event.last_seen)
        trend_result = await session.execute(
            select(
                day_expr.label("dt"),
                func.count(Event.id).label("count"),
            )
            .where(day_expr.between(start_str, end_str))
            .group_by(day_expr)
            .order_by(day_expr)
        )
        trend_map = {str(r.dt): int(r.count or 0) for r in trend_result.all()}

    # 补全日期
    trend = []
    cur = start_dt
    while cur <= now:
        key = cur.strftime("%Y-%m-%d")
        trend.append({"date": cur.strftime("%m-%d"), "count": trend_map.get(key, 0)})
        cur += timedelta(days=1)

    return {
        "total": total_count,
        "by_risk": by_risk,
        "by_status": by_status,
        "by_type": by_type,
        "by_device": by_device,
        "trend": trend,
    }


@router.get("/events/devices")
async def get_event_devices():
    """获取事件中出现过的设备列表（用于筛选下拉）
    优先从 CMDB 解析设备名称，IP 地址会被转换为对应的设备名。
    """
    from models.cmdb import CMDBAsset

    async with async_session_factory() as session:
        # 1. 获取事件中所有不同的 source_device 值
        result = await session.execute(
            select(Event.source_device)
            .where(Event.source_device != "")
            .distinct()
            .order_by(Event.source_device)
        )
        raw_devices = [row[0] for row in result.all() if row[0]]

        # 2. 将所有 IP 形式的 device 通过 CMDB 解析为设备名
        #    先批量查出 CMDB 中 IP→name 映射
        cmdb_result = await session.execute(
            select(CMDBAsset.ip_address, CMDBAsset.name)
            .where(CMDBAsset.ip_address != "")
        )
        ip_to_name = {row[0]: row[1] for row in cmdb_result.all() if row[0] and row[1]}

        # 3. 构建最终设备列表（去重，优先展示设备名）
        seen = set()
        devices = []
        for d in raw_devices:
            display = ip_to_name.get(d, d)  # 如果是 IP，替换为 CMDB 名称
            if display not in seen:
                seen.add(display)
                devices.append(display)

        # 也把 CMDB 中有 IP 但事件中还没出现的设备加进去（便于筛选）
        for ip, name in ip_to_name.items():
            if name not in seen:
                seen.add(name)
                devices.append(name)

        devices.sort()
        return {"devices": devices}


@router.get("/events/{event_id}")
async def get_event(event_id: str):
    """事件详情"""
    from models.cmdb import CMDBAsset

    async with async_session_factory() as session:
        # CMDB IP→name 映射
        cmdb_result = await session.execute(
            select(CMDBAsset.ip_address, CMDBAsset.name)
            .where(CMDBAsset.ip_address != "")
        )
        ip_to_name = {row[0]: row[1] for row in cmdb_result.all() if row[0] and row[1]}

        result = await session.execute(
            select(Event).where(Event.event_id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=404, detail="事件不存在")
        return _serialize_event(event, ip_to_name)


@router.put("/events/batch/status")
async def batch_update_event_status(body: BatchStatusBody):
    """批量更新事件状态"""
    if body.status not in [s.value for s in EventStatus]:
        raise HTTPException(status_code=400, detail="无效的状态值")

    async with async_session_factory() as session:
        result = await session.execute(
            select(Event).where(Event.event_id.in_(body.event_ids))
        )
        events = result.scalars().all()
        if not events:
            raise HTTPException(status_code=404, detail="未找到任何事件")

        for event in events:
            event.status = body.status
        await session.commit()
        return {"message": f"已更新 {len(events)} 条事件状态"}


@router.put("/events/{event_id}/status")
async def update_event_status(event_id: str, body: StatusBody):
    """更新事件状态（接收 JSON body）"""
    status = body.status
    async with async_session_factory() as session:
        result = await session.execute(
            select(Event).where(Event.event_id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=404, detail="事件不存在")

        if status not in [s.value for s in EventStatus]:
            raise HTTPException(status_code=400, detail="无效的状态值")

        event.status = status
        await session.commit()
        return {"message": "状态更新成功"}


def _sse_frame(data: dict) -> str:
    """构建标准 SSE 帧：data:{json}\\n\\n"""
    return "data:" + orjson.dumps(data).decode() + "\n\n"


@router.post("/events/{event_id}/analyze")
async def analyze_event(event_id: str):
    """对单条事件进行 AI 流式分析（SSE）

    返回 text/event-stream，分帧协议：
        data: {"type":"meta","event_id":"..."}\\n\\n
        data: {"type":"content","content":"逐段文本"}\\n\\n
        data: {"type":"finish"}\\n\\n
        data: {"type":"error","content":"错误信息"}\\n\\n
    """
    async with async_session_factory() as session:
        result = await session.execute(select(Event).where(Event.event_id == event_id))
        event = result.scalar_one_or_none()
        if not event:
            async def _err():
                yield _sse_frame({"type": "error", "content": "事件不存在"})
            return StreamingResponse(_err(), media_type="text/event-stream")

    # 获取默认模型配置
    model_cfg = await model_scheduler.get_model()
    if not model_cfg:
        async def _err():
            yield _sse_frame({"type": "error", "content": "没有可用的模型配置"})
        return StreamingResponse(_err(), media_type="text/event-stream")

    # 构建事件上下文
    event_text = f"""事件ID: {event.event_id}
事件类型: {event.event_type}
风险等级: {event.risk_level.value if hasattr(event.risk_level, 'value') else event.risk_level}
设备: {event.source_device or '-'}
源IP: {event.source_ip or '-'}
状态: {event.status.value if hasattr(event.status, 'value') else event.status}
首次发现: {to_cst(event.first_seen)}
最近发现: {to_cst(event.last_seen)}
累计触发: {event.occurrence_count or 1} 次
摘要: {event.summary or '-'}
原始日志: {event.raw_log or '-'}
"""

    messages = [
        {
            "role": "system",
            "content": (
                "你是 AIOps 智能运维平台的专家分析助手。"
                "请基于提供的事件信息，给出结构化的分析结论。"
                "分析应包括：1) 事件概述；2) 可能原因；3) 影响范围；4) 处置建议。"
                "使用 Markdown 格式输出。"
            ),
        },
        {"role": "user", "content": f"请分析以下事件：\n\n{event_text}"},
    ]

    async def _stream_generator():
        yield _sse_frame({"type": "meta", "event_id": event_id})
        full_text = ""
        try:
            async for chunk in llm_client.stream_chat(
                messages=messages,
                model=model_cfg["model_name"],
                temperature=model_cfg.get("temperature", 0.7),
                max_tokens=4096,
                api_base=model_cfg.get("api_base"),
                api_key=model_cfg.get("api_key"),
            ):
                content = chunk.get("content", "")
                if content:
                    full_text += content
                    yield _sse_frame({"type": "content", "content": content})
        except Exception as e:
            err_msg = f"大模型分析失败: {str(e)[:300]}"
            print(f"[AIOPS][request_id={get_request_id()}] 事件分析异常: {err_msg}")
            yield _sse_frame({"type": "error", "content": err_msg})
            return

        # 可选：将分析结果保存到 ai_report 字段
        try:
            event.ai_report = {"analysis": full_text, "analyzed_at": to_cst(__import__('datetime').datetime.utcnow())}
            async with async_session_factory() as session:
                await session.merge(event)
                await session.commit()
        except Exception as e:
            print(f"[AIOPS][request_id={get_request_id()}] 保存事件分析结果失败: {e}")

        yield _sse_frame({"type": "finish", "event_id": event_id})

    return StreamingResponse(_stream_generator(), media_type="text/event-stream")