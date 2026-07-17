"""数据源配置模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, func
from core.db import Base


class Datasource(Base):
    __tablename__ = "datasources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, comment="数据源名称")
    ds_type = Column(String(32), nullable=False, comment="类型: es/mysql/redis")
    host = Column(String(256), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(128))
    password = Column(String(256))
    extra_config = Column(JSON, comment="额外配置")
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())