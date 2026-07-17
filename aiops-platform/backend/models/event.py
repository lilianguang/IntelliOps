"""事件中心 + 告警相关模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Enum, BigInteger, func, Index
from core.db import Base
from models.keyword import RiskLevel
import enum


class EventStatus(str, enum.Enum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class Event(Base):
    """事件主表"""
    __tablename__ = "events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(String(36), unique=True, nullable=False)
    skill_id = Column(Integer, nullable=False)
    event_type = Column(String(64), nullable=False)
    risk_level = Column(Enum(RiskLevel, values_callable=lambda x: [e.value for e in x]), nullable=False)
    summary = Column(Text)
    source_device = Column(String(128))
    source_ip = Column(String(64))
    raw_log = Column(Text)
    ai_report = Column(JSON)
    status = Column(Enum(EventStatus, values_callable=lambda x: [e.value for e in x]), default=EventStatus.NEW)
    occurrence_count = Column(Integer, default=1)
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_skill", "skill_id"),
        Index("idx_risk", "risk_level"),
        Index("idx_status", "status"),
        Index("idx_last_seen", "last_seen"),
        Index("idx_device", "source_ip"),
    )


class EventFingerprint(Base):
    """事件去重指纹表"""
    __tablename__ = "event_fingerprints"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    fingerprint = Column(String(64), unique=True, nullable=False, comment="MD5指纹")
    event_id = Column(String(36), nullable=False)
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    count = Column(Integer, default=1)
    suppressed = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_fingerprint", "fingerprint"),
        Index("idx_suppressed", "suppressed"),
    )


class AlertLog(Base):
    """告警日志"""
    __tablename__ = "alert_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(String(36), nullable=False)
    channel_id = Column(Integer, nullable=False)
    status = Column(String(32), comment="success/failed")
    result = Column(Text)
    error_msg = Column(Text)
    created_at = Column(DateTime, server_default=func.now())