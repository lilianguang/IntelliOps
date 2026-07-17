"""网络设备日志分析技能 (h3c-net-logs-*) - v3.0 增强版"""

from skills.base import BaseSkill, SkillResult
from core.llm_client import llm_client
from gateway.prompt_mgr import prompt_mgr
from skills.registry import skill_registry
import json


class H3CNetSkill(BaseSkill):
    """网络设备日志分析技能"""
    name = "h3c-net-analysis"
    description = "分析H3C交换机、路由器等网络设备日志，支持情绪扫描和命令行为分析"

    async def execute(self, query: str, time_range: str, logs: list) -> dict:
        """执行网络设备日志分析"""
        prompt = await prompt_mgr.get_prompt(
            "h3c_net_analysis.tpl",
            time_range=time_range,
            logs=json.dumps(logs[:50], ensure_ascii=False, indent=2)[:8000],
        )
        try:
            response = await llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return {
                "summary": response[:200],
                "risk_level": "medium",
                "report": {"content": response},
            }
        except Exception as e:
            return {"summary": f"AI分析失败: {str(e)}", "risk_level": "low", "report": {}}

    async def analyze_logs(self, logs: list, analysis_type: str) -> str:
        """对日志执行特定类型的AI分析"""
        if not logs:
            return "没有日志数据"

        log = logs[0]  # 分析单条日志

        template_map = {
            "emotion_scan": "emotion_scan.tpl",
            "command_analysis": "command_analysis.tpl",
            "root_cause": "h3c_net_analysis.tpl",
        }

        template_name = template_map.get(analysis_type, "h3c_net_analysis.tpl")
        prompt = await prompt_mgr.get_prompt(
            template_name,
            severity=log.get("severity", ""),
            message=log.get("message", ""),
            device_ip=log.get("device_ip", ""),
            hostname=log.get("hostname", ""),
            user=log.get("user", ""),
            src_ip=log.get("src_ip", ""),
            command=log.get("command", ""),
            event_name=log.get("event_name", ""),
            logs=json.dumps(log, ensure_ascii=False, indent=2),
            time_range="5m",
        )

        try:
            return await llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
        except Exception as e:
            return f"[AI分析失败] {str(e)}"


# 注册技能
skill_registry.register(H3CNetSkill())