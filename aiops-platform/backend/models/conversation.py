"""对话记录模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Enum, func, Index
from core.db import Base
from models.keyword import RiskLevel


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(36), unique=True, nullable=False, comment="对话UUID")
    tenant = Column(String(64), comment="租户")
    user = Column(String(64), comment="用户")
    skill = Column(String(64), comment="技能标识")
    title = Column(String(128), comment="会话标题")
    query = Column(Text, comment="用户问题")
    summary = Column(Text, comment="AI摘要")
    risk_level = Column(Enum(RiskLevel, values_callable=lambda x: [e.value for e in x]), default=RiskLevel.LOW)
    full_report = Column(JSON, comment="完整报告")
    archived = Column(Integer, default=0, comment="是否归档: 0=否, 1=是")
    messages = Column(JSON, comment="多轮消息数组: [{role,content,risk_level,created_at}]")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_archived", "archived"),
        Index("idx_created", "created_at"),
        Index("idx_user", "user"),
    )