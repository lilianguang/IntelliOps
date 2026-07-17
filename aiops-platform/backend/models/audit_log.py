"""审计日志模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, BigInteger, func, Index
from core.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String(64), nullable=False)
    action = Column(String(64), nullable=False, comment="login/logout/create/update/delete")
    target = Column(String(128), comment="操作对象")
    detail = Column(JSON, comment="操作详情")
    ip_address = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_user", "user_id"),
        Index("idx_action", "action"),
        Index("idx_created", "created_at"),
    )