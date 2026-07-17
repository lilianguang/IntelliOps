"""故障事件综合分析技能 (跨索引综合)"""

from skills.base import BaseSkill
from core.llm_client import llm_client
from gateway.prompt_mgr import prompt_mgr
from skills.registry import skill_registry
import json


class IncidentSkill(BaseSkill):
    name = "incident-analysis"
    description = "综合故障事件根因分析（跨索引综合技能）"

    async def execute(self, query: str, time_range: str, logs: list) -> dict:
        prompt = await prompt_mgr.get_prompt(
            "incident_analysis.tpl",
            time_range=time_range,
            logs=json.dumps(logs[:50], ensure_ascii=False, indent=2)[:8000],
        )
        try:
            response = await llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return {"summary": response[:200], "risk_level": "high", "report": {"content": response}}
        except Exception as e:
            return {"summary": f"AI分析失败: {str(e)}", "risk_level": "low", "report": {}}

    async def analyze_logs(self, logs: list, analysis_type: str) -> str:
        return ""


skill_registry.register(IncidentSkill())