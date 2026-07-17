"""v3.0 新增：规则配置模型"""

from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, JSON, Enum, func, Index
from core.db import Base
from models.keyword import RiskLevel
import enum


class RuleType(str, enum.Enum):
    SEVERITY_FILTER = "severity_filter"
    COMMAND_MONITOR = "command_monitor"
    DANGEROUS_COMMAND = "dangerous_command"
    HTTP_STATUS_ALERT = "http_status_alert"
    RESPONSE_TIME_ALERT = "response_time_alert"
    KEYWORD_MATCH = "keyword_match"
    AI_ANALYSIS_TRIGGER = "ai_analysis_trigger"
    IGNORE_RULE = "ignore_rule"
    METRIC_THRESHOLD = "metric_threshold"


class Rule(Base):
    """规则配置表 - v3.0新增"""
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_name = Column(String(64), nullable=False)
    skill_id = Column(Integer, nullable=False)
    rule_type = Column(Enum(RuleType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    match_condition = Column(JSON, nullable=False, comment="匹配条件")
    exclude_condition = Column(JSON, comment="排除条件")
    risk_level = Column(Enum(RiskLevel, values_callable=lambda x: [e.value for e in x]), default=RiskLevel.MEDIUM)
    action_config = Column(JSON, nullable=False, comment="动作配置")
    priority = Column(Integer, default=0, comment="优先级(越小越优先)")
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_skill", "skill_id"),
        Index("idx_type", "rule_type"),
        Index("idx_enabled", "enabled"),
    )


class AlertStormConfig(Base):
    """告警风暴配置表 - v3.0新增"""
    __tablename__ = "alert_storm_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    skill_id = Column(Integer, nullable=False)
    rule_id = Column(Integer, comment="关联规则(NULL=全局)")
    window_minutes = Column(Integer, default=5, comment="时间窗口(分钟)")
    max_count = Column(Integer, default=10, comment="窗口内最大告警次数")
    action_on_storm = Column(String(16), default="digest", comment="digest/suppress/escalate")
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_skill", "skill_id"),)


class AIAnalysisConfig(Base):
    """AI分析配置表 - v3.0新增"""
    __tablename__ = "ai_analysis_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    skill_id = Column(Integer, nullable=False)
    trigger_type = Column(String(16), nullable=False, comment="periodic/on_alert/severity_match/command_match/manual")
    cron_expression = Column(String(32), comment="cron表达式(仅periodic)")
    analysis_type = Column(String(32), nullable=False, comment="分析类型")
    analysis_params = Column(JSON, comment="分析参数")
    prompt_template = Column(String(64), comment="Prompt模板")
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_skill", "skill_id"),)


class AlertStormEvent(Base):
    """风暴事件记录表 - v3.0新增"""
    __tablename__ = "alert_storm_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, nullable=False)
    fingerprint = Column(String(64), nullable=False, comment="风暴指纹")
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    count = Column(Integer, default=1)
    suppressed = Column(Integer, default=0)
    digest_sent = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_fingerprint", "fingerprint"),
        Index("idx_suppressed", "suppressed"),
    )