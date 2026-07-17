"""大模型配置模型"""

from sqlalchemy import Column, Integer, String, Float, DateTime, func
from core.db import Base


class LLMConfig(Base):
    __tablename__ = "llm_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, comment="配置名称")
    model_name = Column(String(64), nullable=False, comment="模型名称")
    api_base = Column(String(256), nullable=False, comment="API地址")
    api_key = Column(String(256), nullable=False, comment="API密钥")
    temperature = Column(Float, default=0.7)
    priority = Column(Integer, default=0, comment="优先级: 0=主, 1=备")
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())