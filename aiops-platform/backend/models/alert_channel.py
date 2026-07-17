"""告警渠道配置模型"""

from sqlalchemy import Column, Integer, String, DateTime, JSON, func
from core.db import Base


class AlertChannel(Base):
    __tablename__ = "alert_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, comment="渠道名称")
    channel_type = Column(String(32), nullable=False, comment="类型: dingtalk/email/webhook")
    config = Column(JSON, nullable=False, comment="渠道配置(JSON)")
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())