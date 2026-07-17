"""用户权限模型"""

from sqlalchemy import Column, Integer, String, DateTime, Enum, func, Index
from core.db import Base
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CONFIG = "config"
    AUDIT = "audit"
    USER = "user"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    display_name = Column(String(64))
    role = Column(Enum(UserRole, values_callable=lambda x: [e.value for e in x]), default=UserRole.USER, nullable=False)
    email = Column(String(128))
    phone = Column(String(32))
    enabled = Column(Integer, default=1)
    last_login = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_role", "role"),
        Index("idx_enabled", "enabled"),
    )