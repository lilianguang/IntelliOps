"""报告生成引擎"""

from core.llm_client import llm_client
from gateway.prompt_mgr import prompt_mgr
from api.chat import _enrich_with_cmdb
import json


class ReportGenerator:
    """报告生成引擎"""

    async def generate_report(self, skill_name: str, logs: list, time_range: str) -> dict:
        """生成AI分析报告"""
        template_map = {
            "h3c-net-analysis": "network_report.tpl",
            "nginx-access-analysis": "application_report.tpl",
            "storage-analysis": "storage_report.tpl",
            "security-analysis": "security_report.tpl",
            "incident-analysis": "network_report.tpl",
            "prometheus-net": "system_report.tpl",
        }

        template_name = template_map.get(skill_name, "network_report.tpl")
        logs_text = json.dumps(logs[:50], ensure_ascii=False, indent=2)[:8000]
        prompt = await prompt_mgr.get_prompt(
            template_name,
            time_range=time_range,
            logs=logs_text,
        )

        # CMDB 资产关联：从日志数据中提取 IP，查询 CMDB 资产表，注入设备名称/区域信息
        cmdb_context = await _enrich_with_cmdb(logs_text)
        if cmdb_context:
            prompt += (
                "\n\n---\n"
                "## CMDB 资产关联\n"
                "以下 IP 已在资产库中登记，请在报告中用设备名称替代纯 IP，"
                "按区域/机房维度归纳问题，并提及负责人：\n"
                f"{cmdb_context}\n"
            )

        response = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )

        return {
            "title": f"{skill_name} 分析报告",
            "content": response,
            "time_range": time_range,
        }


# 全局单例
report_generator = ReportGenerator()