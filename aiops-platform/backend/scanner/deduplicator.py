"""事件去重引擎"""

from datetime import datetime, timedelta
from core.db import async_session_factory
from models.event import Event, EventFingerprint
from sqlalchemy import select
import hashlib


class EventDeduplicator:
    """事件去重引擎"""

    async def is_duplicate(self, device_ip: str, event_type: str, keyword: str) -> bool:
        """判断是否重复事件"""
        fingerprint = self._generate_fingerprint(device_ip, event_type, keyword)

        async with async_session_factory() as session:
            result = await session.execute(
                select(EventFingerprint).where(
                    EventFingerprint.fingerprint == fingerprint,
                    EventFingerprint.suppressed == 0,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # 更新计数和时间
                existing.count += 1
                existing.last_seen = datetime.now()
                await session.commit()
                return True

            # 记录新指纹
            new_fp = EventFingerprint(
                fingerprint=fingerprint,
                event_id="",  # 待关联
                first_seen=datetime.now(),
                last_seen=datetime.now(),
            )
            session.add(new_fp)
            await session.commit()
            return False

    def _generate_fingerprint(self, device_ip: str, event_type: str, keyword: str) -> str:
        """生成MD5指纹"""
        raw = f"{device_ip}:{event_type}:{keyword}"
        return hashlib.md5(raw.encode()).hexdigest()


# 全局单例
event_dedup = EventDeduplicator()