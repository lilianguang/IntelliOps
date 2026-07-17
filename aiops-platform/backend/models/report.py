"""分析报告模型"""

from sqlalchemy import Column, Integer, String, DateTime, JSON, func
from core.db import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(36), nullable=False, comment="关联对话ID")
    report_content = Column(JSON, nullable=False, comment="报告内容")
    created_at = Column(DateTime, server_default=func.now())