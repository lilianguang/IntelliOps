"""技能执行引擎"""

from typing import Optional, List
from skills.registry import skill_registry
from core.es_client import es_client
from core.llm_client import llm_client
from gateway.prompt_mgr import prompt_mgr
import json


class SkillEngine:
    """技能执行引擎"""

    async def execute(self, skill_name: str, query: str, time_range: str = "30m") -> dict:
        """执行技能"""
        skill = skill_registry.get(skill_name)
        if not skill:
            return {"error": f"技能 {skill_name} 不存在"}

        # 检索ES日志
        logs = await self._search_logs(skill_name, time_range)

        # 执行技能分析
        result = await skill.execute(query, time_range, logs)
        return result

    async def analyze(self, skill_name: str, logs: List[dict], analysis_type: str) -> str:
        """执行特定类型的AI分析"""
        skill = skill_registry.get(skill_name)
        if not skill:
            return f"技能 {skill_name} 不存在"
        return await skill.analyze_logs(logs, analysis_type)

    async def _search_logs(self, skill_name: str, time_range: str) -> list:
        """根据技能名称检索ES"""
        from core.db import async_session_factory
        from models.skill import Skill
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(
                select(Skill).where(Skill.skill_name == skill_name)
            )
            skill = result.scalar_one_or_none()

        if not skill:
            return []

        # 解析时间范围
        seconds = self._parse_time_range(time_range)
        es_query = {
            "query": {
                "bool": {
                    "filter": [{"range": {"@timestamp": {
                        "gte": f"now-{seconds}s", "lte": "now"
                    }}}]
                }
            },
            "sort": [{"@timestamp": "desc"}],
            "size": 100,
        }

        try:
            result = await es_client.search(skill.index_pattern, es_query)
            hits = result.get("hits", {}).get("hits", [])
            return [hit["_source"] for hit in hits]
        except Exception:
            return []

    def _parse_time_range(self, time_range: str) -> int:
        unit = time_range[-1]
        value = int(time_range[:-1])
        if unit == "m": return value * 60
        if unit == "h": return value * 3600
        if unit == "d": return value * 86400
        return 300


# 全局单例
skill_engine = SkillEngine()