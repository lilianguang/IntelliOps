"""技能注册中心"""

from typing import Dict, Optional
from skills.base import BaseSkill


class SkillRegistry:
    """技能注册中心"""

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill):
        """注册技能"""
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[BaseSkill]:
        """获取技能"""
        return self._skills.get(name)

    def list_skills(self) -> dict:
        """列出所有技能"""
        return {name: skill.description for name, skill in self._skills.items()}


# 全局单例
skill_registry = SkillRegistry()