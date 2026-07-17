"""存储日志分析技能 (ops-storage-logs-*)"""

from skills.base import BaseSkill
from core.llm_client import llm_client
from gateway.prompt_mgr import prompt_mgr
from skills.registry import skill_registry
import json


class StorageSkill(BaseSkill):
    name = "storage-analysis"
    description = "分析存储设备及光纤交换机日志"

    async def execute(self, query: str, time_range: str, logs: list) -> dict:
        prompt = await prompt_mgr.get_prompt(
            "storage_analysis.tpl",
            time_range=time_range,
            logs=json.dumps(logs[:50], ensure_ascii=False, indent=2)[:8000],
        )
        try:
            response = await llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return {"summary": response[:200], "risk_level": "medium", "report": {"content": response}}
        except Exception as e:
            return {"summary": f"AI分析失败: {str(e)}", "risk_level": "low", "report": {}}

    async def analyze_logs(self, logs: list, analysis_type: str) -> str:
        return ""


skill_registry.register(StorageSkill())