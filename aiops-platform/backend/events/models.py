"""事件中心模型"""

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class EventModel(BaseModel):
    """事件数据模型"""
    event_id: str
    skill_id: int
    event_type: str
    risk_level: str
    summary: str = ""
    source_device: str = ""
    source_ip: str = ""
    raw_log: str = ""
    ai_report: Optional[dict] = None
    status: str = "new"
    occurrence_count: int = 1
    first_seen: datetime = None
    last_seen: datetime = None