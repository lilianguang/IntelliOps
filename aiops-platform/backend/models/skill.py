"""技能配置模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, func, Index
from core.db import Base


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    datasource_id = Column(Integer, comment="关联数据源ID")
    ds_type = Column(String(32), default="es", comment="数据源类型: es/prometheus/...")
    skill_name = Column(String(64), unique=True, nullable=False, comment="技能标识")
    display_name = Column(String(64), nullable=False, comment="展示名称")
    description = Column(Text, comment="功能描述")
    index_pattern = Column(String(128), comment="ES索引模式(兼容旧版)")
    field_schema = Column(Text, comment="ES字段说明JSON：[{name,type,desc,example}]")
    query_filter = Column(Text, comment="ES查询过滤条件JSON：{logic:AND/OR,conditions:[{field,operator,value}]}")
    query_config = Column(JSON, comment="查询配置JSON(按ds_type动态结构)")
    prompt_template = Column(String(64), nullable=False, comment="Prompt模板文件名")
    model = Column(String(32), default="qwen3", comment="默认模型")
    scan_interval_sec = Column(Integer, default=300, comment="扫描间隔(秒)")
    keyword_matching = Column(Integer, default=1, comment="启用关键字匹配")
    anomaly_detection = Column(Integer, default=0, comment="启用AI异常检测")
    enabled = Column(Integer, default=1, comment="是否启用")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_enabled", "enabled"),
        Index("idx_pattern", "index_pattern"),
        Index("idx_datasource", "datasource_id"),
    )