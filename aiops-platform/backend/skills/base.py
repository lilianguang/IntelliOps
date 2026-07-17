"""技能基类 - 所有技能的抽象基类"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseSkill(ABC):
    """技能基类"""

    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(self, query: str, time_range: str, logs: list) -> dict:
        """执行技能分析"""
        pass

    @abstractmethod
    async def analyze_logs(self, logs: list, analysis_type: str) -> str:
        """对日志执行特定的AI分析"""
        pass


class SkillResult:
    """技能执行结果"""
    def __init__(self, summary: str = "", risk_level: str = "low", report: Optional[dict] = None):
        self.summary = summary
        self.risk_level = risk_level
        self.report = report or {}