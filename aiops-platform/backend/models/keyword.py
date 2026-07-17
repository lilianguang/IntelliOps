"""事件关键字模型（v3.0可废弃，合并到rules表）"""

from sqlalchemy import Column, Integer, String, DateTime, Enum, func
from core.db import Base
import enum


class MatchType(str, enum.Enum):
    EXACT = "exact"
    CONTAINS = "contains"
    REGEX = "regex"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventKeyword(Base):
    __tablename__ = "event_keywords"

    id = Column(Integer, primary_key=True, autoincrement=True)
    skill_id = Column(Integer, nullable=False, comment="关联技能ID")
    keyword = Column(String(128), nullable=False, comment="关键字")
    match_type = Column(Enum(MatchType), default=MatchType.CONTAINS)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.MEDIUM)
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())