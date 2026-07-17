"""事件存储"""

from datetime import datetime
import uuid
from core.db import async_session_factory
from models.event import Event, EventFingerprint
from sqlalchemy import select


class EventRepository:
    """事件存储"""

    async def save_event(self, skill_id: int, event_type: str, risk_level: str,
                          summary: str, source_device: str = "", source_ip: str = "",
                          raw_log: str = "", ai_report: dict = None) -> Event:
        """保存事件"""
        async with async_session_factory() as session:
            event = Event(
                event_id=str(uuid.uuid4()),
                skill_id=skill_id,
                event_type=event_type,
                risk_level=risk_level,
                summary=summary[:500] if summary else "",
                source_device=source_device,
                source_ip=source_ip,
                raw_log=raw_log[:2000] if raw_log else "",
                ai_report=ai_report,
                first_seen=datetime.now(),
                last_seen=datetime.now(),
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)
            return event

    async def get_event(self, event_id: str) -> Event:
        """获取事件"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Event).where(Event.event_id == event_id)
            )
            return result.scalar_one_or_none()


# 全局单例
event_repository = EventRepository()