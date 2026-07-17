"""Prompt管理器 - 加载和管理Prompt模板"""

from typing import Optional
from pathlib import Path


class PromptManager:
    """Prompt模板管理器"""

    def __init__(self, template_dir: str = None):
        self._template_dir = Path(template_dir or "config/prompts")
        self._cache = {}

    async def get_prompt(self, template_name: str, **kwargs) -> str:
        """
        获取渲染后的Prompt

        Args:
            template_name: 模板文件名（如 h3c_net_analysis.tpl）
            **kwargs: 模板变量
        Returns:
            渲染后的Prompt文本
        """
        template = await self._load_template(template_name)
        return self._render(template, **kwargs)

    async def _load_template(self, name: str) -> str:
        """加载模板（带缓存）"""
        if name in self._cache:
            return self._cache[name]

        template_path = self._template_dir / name
        if not template_path.exists():
            # 如果模板不存在，返回默认模板
            return self._get_default_template(name)

        template = template_path.read_text(encoding="utf-8")
        self._cache[name] = template
        return template

    def _render(self, template: str, **kwargs) -> str:
        """简单模板渲染（后续可升级为 Jinja2）"""
        result = template
        for key, value in kwargs.items():
            placeholder = "{{" + key + "}}"
            result = result.replace(placeholder, str(value))
        return result

    def _get_default_template(self, name: str) -> str:
        """获取默认模板（文件不存在时的回退模板）"""
        templates = {
            # ===== 分析模板（用于对话 QA 模式） =====
            "h3c_net_analysis.tpl": """你是一个网络运维专家，请分析以下网络设备日志：

查询时间范围: {{time_range}}
日志数据: {{logs}}

请按以下格式输出分析报告：
1. 故障摘要
2. 异常时间
3. 涉及设备
4. 影响范围
5. 根因分析
6. 风险等级
7. 关联日志
8. 处置建议
9. 预防建议""",

            "nginx_access_analysis.tpl": """你是一个Web运维专家，请分析以下Nginx访问日志：

查询时间范围: {{time_range}}
日志数据: {{logs}}

请分析：
1. 状态码分布
2. 响应时间异常
3. URL访问频次
4. 域名维度统计
5. 问题分析与建议""",

            "emotion_scan.tpl": """你是一个日志情绪分析专家，请分析以下日志的情绪倾向：

日志级别: {{severity}}
日志内容: {{message}}

请分析：
1. 情绪标签（紧急/警告/错误/严重/常规）
2. 严重程度评分（0-10）
3. 是否需要人工介入""",

            "command_analysis.tpl": """你是一个网络运维安全专家，请分析以下命令执行记录：

设备IP: {{device_ip}}
设备名称: {{hostname}}
操作者: {{user}}
来源IP: {{src_ip}}
执行命令: {{command}}
事件名称: {{event_name}}

请分析：
1. 命令执行上下文
2. 是否同设备连续操作
3. 风险评估
4. 是否关联其他事件""",

            "nginx_business_report.tpl": """你是一个Web业务分析专家，请基于以下Nginx访问数据生成业务分析报告：

数据维度: {{dimensions}}
时间范围: {{time_range}}
聚合数据: {{aggregated_data}}

请生成报告：
1. 整体访问概况
2. 状态码分析
3. 响应时间TOP N
4. 业务系统分析
5. 趋势变化
6. 优化建议""",

            # ===== 报告模板（用于智能报告 Report 模式，文件版优先） =====
            "network_report.tpl": """你是一个资深网络运维专家，请基于以下数据生成智能运维分析报告：

时间范围: {{time_range}}
运维数据: {{logs}}

请输出包含以下章节的报告：一、摘要（风险概览+健康评分）二、风险排行 三、详细报告（设备性能/接口健康/日志分析/运维操作）四、AI总结与建议（风险总结/优先事项/趋势预测/健康评分）""",

            "security_report.tpl": """你是一个资深网络安全专家，请基于以下数据生成安全态势分析报告：

时间范围: {{time_range}}
安全数据: {{logs}}

请输出包含以下章节的报告：一、安全态势摘要 二、威胁排行 三、详细安全报告（攻击检测/入侵防御/异常流量/安全运维）四、AI安全总结与建议""",

            "application_report.tpl": """你是一个资深应用运维专家，请基于以下数据生成应用健康分析报告：

时间范围: {{time_range}}
应用数据: {{logs}}

请输出包含以下章节的报告：一、应用健康摘要 二、风险排行 三、详细报告（访问概况/状态码/性能/异常检测）四、AI总结与建议""",

            "system_report.tpl": """你是一个资深 SRE/系统运维专家，请基于以下数据生成系统健康分析报告：

时间范围: {{time_range}}
监控数据: {{logs}}

请输出包含以下章节的报告：一、系统健康摘要 二、风险排行 三、详细报告（计算/存储/网络/服务）四、AI总结与建议（含容量趋势预测）""",

            "storage_report.tpl": """你是一个资深存储运维专家，请基于以下数据生成存储健康分析报告：

时间范围: {{time_range}}
存储数据: {{logs}}

请输出包含以下章节的报告：一、存储健康摘要 二、风险排行 三、详细报告（容量/性能/硬件/告警）四、AI总结与建议""",
        }
        return templates.get(name, "请分析以下日志数据：\n{{logs}}")


# 全局单例
prompt_mgr = PromptManager()