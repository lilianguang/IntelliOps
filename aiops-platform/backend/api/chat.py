"""对话 API - AI对话接口（流式重构版）

借鉴 SQLBot 的 SSE 流式架构：
- StreamingResponse(media_type="text/event-stream")
- 分帧协议：meta → content* → finish / error
- 流式过程中实时累积完整文本，结束后一次性持久化

保留 POST /chat 非流式端点向后兼容。
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
import uuid
import json
import orjson
from sqlalchemy import select
from gateway.router import skill_router
from gateway.prompt_mgr import prompt_mgr
from gateway.model_scheduler import model_scheduler
from core.llm_client import llm_client
from core.es_client import es_client
from core.db import async_session_factory
from core.prometheus_client import get_prometheus_client
from models.skill import Skill
from models.datasource import Datasource
from models.conversation import Conversation
from models.cmdb import CMDBAsset
from api.auth import get_current_user
import re

router = APIRouter()

# 中国标准时间 UTC+8
CST = timezone(timedelta(hours=8))
# 多轮上下文窗口：最近 N 条历史消息传给大模型
MAX_CONTEXT_MESSAGES = 6
# 聚合模式：传给大模型的格式化统计文本最大字符数
STATS_MAX_CHARS = 15000
# 无字段配置时的回退采样日志条数
FALLBACK_SAMPLE_SIZE = 50
# ES 聚合查询的每个 terms 桶数量上限
AGGS_TERMS_SIZE = 20
# 时间趋势聚合的目标桶数（date_histogram）
AGGS_TIME_BUCKETS = 30
# 聚合模式下同时获取的最新样本日志条数（让 LLM 能看到具体命令/配置变更内容）
AGG_SAMPLE_SIZE = 30
# 单条样本日志字段值最大字符数（防止超长文本撑爆上下文）
SAMPLE_FIELD_MAX_LEN = 200
# 命令执行日志专项查询条数（含 command 字段的技能单独拉取全部命令记录，避免被其他日志类型淹没）
COMMAND_LOG_SIZE = 5000
# 单条命令日志的 command 字段最大字符数（命令可能较长，给予更大配额）
COMMAND_MAX_LEN = 500
# 命令日志传给 LLM 的最大字符数（独立于 STATS_MAX_CHARS，不与聚合数据争抢空间）
COMMAND_MAX_CONTEXT = 30000
# CMDB 资产上下文注入最大字符数
CMDB_CONTEXT_MAX_CHARS = 3000
# IP 正则（匹配 IPv4 地址）
_IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')


# ====================================================================
#  CMDB 资产关联 —— 从数据中提取 IP，查询 CMDB 注入设备名称/区域
# ====================================================================
def _extract_ips_from_text(text: str, max_ips: int = 50) -> set:
    """从文本中提取所有 IPv4 地址（去重，最多返回 max_ips 个）"""
    if not text:
        return set()
    ips = set(_IP_RE.findall(text))
    # 过滤掉无效 IP（每段 > 255）
    valid = set()
    for ip in ips:
        parts = ip.split('.')
        if all(0 <= int(p) <= 255 for p in parts):
            valid.add(ip)
        if len(valid) >= max_ips:
            break
    return valid


async def _query_cmdb_by_ips(ips: set) -> list:
    """根据 IP 集合查询 CMDB 资产，返回匹配的资产列表"""
    if not ips:
        return []
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(CMDBAsset).where(CMDBAsset.ip_address.in_(list(ips)))
            )
            assets = result.scalars().all()
            return [
                {
                    "ip": a.ip_address,
                    "name": a.name,
                    "asset_code": a.asset_code,
                    "asset_type": a.asset_type,
                    "region": a.region,
                    "datacenter": a.datacenter,
                    "owner": a.owner,
                    "status": a.status,
                    "organization": a.organization,
                }
                for a in assets if a.ip_address
            ]
    except Exception as e:
        print(f"[AIOPS] CMDB资产查询失败: {e}")
        return []


def _format_cmdb_context(assets: list) -> str:
    """将 CMDB 资产列表格式化为 LLM 上下文文本"""
    if not assets:
        return ""
    lines = ["\n## CMDB 资产关联信息"]
    lines.append("以下 IP 地址已在 CMDB 资产库中登记，请在分析中引用设备名称和区域信息：")
    lines.append("| IP地址 | 设备名称 | 编号 | 类型 | 区域 | 机房 | 负责人 | 状态 |")
    lines.append("|--------|--------|------|------|------|------|--------|------|")
    for a in assets:
        status_label = {
            "online": "在线", "offline": "离线",
            "maintenance": "维护中", "decommissioned": "已报废"
        }.get(a.get("status", ""), a.get("status", "-"))
        lines.append(
            f"| {a['ip']} "
            f"| {a.get('name', '-')} "
            f"| {a.get('asset_code', '-')} "
            f"| {a.get('asset_type', '-')} "
            f"| {a.get('region', '-')} "
            f"| {a.get('datacenter', '-')} "
            f"| {a.get('owner', '-')} "
            f"| {status_label} |"
        )
    return "\n".join(lines)


async def _enrich_with_cmdb(text: str) -> str:
    """从文本中提取 IP，查询 CMDB 资产，返回格式化的上下文文本。
    如果无匹配资产则返回空字符串。"""
    ips = _extract_ips_from_text(text)
    if not ips:
        return ""
    assets = await _query_cmdb_by_ips(ips)
    if not assets:
        return ""
    cmdb_text = _format_cmdb_context(assets)
    print(f"[AIOPS] CMDB关联: 提取{len(ips)}个IP, 匹配{len(assets)}个资产")
    return cmdb_text[:CMDB_CONTEXT_MAX_CHARS]


def _convert_logs_tz(logs: list) -> list:
    """将日志中的时间戳字段从 UTC 转换为东八区（UTC+8）后格式化为可读字符串。

    ES 中 @timestamp 等字段通常以 UTC 存储（如 2026-06-26T07:17:46.123Z），
    直接传给大模型会导致报告中的时间与北京时间差 8 小时。
    本函数在 Python 层统一做转换，确保传给 LLM 的时间就是东八区。
    """
    ts_fields = (
        "@timestamp", "timestamp", "time",
        "create_time", "createTime", "@event_time", "event_time",
    )
    for log in logs:
        if not isinstance(log, dict):
            continue
        for field in ts_fields:
            val = log.get(field)
            if not val or not isinstance(val, str):
                continue
            try:
                raw = val.strip()
                if raw.endswith("Z"):
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                elif len(raw) > 6 and raw[-6] in ("+", "-") and raw[4] == "-":
                    # 已带时区偏移，如 2026-06-26T07:17:46+00:00
                    dt = datetime.fromisoformat(raw)
                else:
                    # 无时区信息，假定为 UTC
                    dt = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
                log[field] = dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pass  # 解析失败则保持原值
    return logs


def _format_time_range(time_range: str, start_time: str = None, end_time: str = None) -> str:
    """将时间范围格式化为中文可读形式，支持自定义时间段。"""
    if start_time and end_time:
        return f"自定义时间段（{start_time} 至 {end_time}）"
    unit_map = {"m": "分钟", "h": "小时", "d": "天"}
    if not time_range:
        return "最近 30 分钟"
    unit = time_range[-1]
    value = time_range[:-1]
    if unit in unit_map and value.isdigit():
        return f"最近 {int(value)} {unit_map[unit]}"
    return f"最近 {time_range}"


# ====================================================================
#  请求 / 响应模型
# ====================================================================
class ChatRequest(BaseModel):
    tenant: str = "ops"
    conversation_id: Optional[str] = None
    skill: Optional[str] = None
    skills: Optional[List[str]] = None  # 多技能联合分析
    query: str
    time_range: str = "30m"
    start_time: Optional[str] = None  # 自定义时间范围开始（ISO 8601 或 datetime 字符串）
    end_time: Optional[str] = None    # 自定义时间范围结束
    stream: bool = False


class ChatResponse(BaseModel):
    request_id: str
    skill: str
    summary: str
    risk_level: str
    report: Optional[dict] = None


def _extract_time_from_query(query: str, default_range: str) -> str:
    """从用户自然语言中提取时间范围，覆盖前端传入的默认值。

    解决场景：用户在对话中说"最近24小时"“近三天”等，但前端下拉框
    可能仍是默认的 30m，导致 ES 查询时间窗口与用户意图不匹配。

    支持的模式：
    - "最近N分钟/小时/天"
    - "近N小时/天"
    - "过去N小时/天"
    - "今Nh" "今Nd"
    - "last N hours/days/minutes"

    返回: 解析后的 time_range 字符串（如 '24h', '3d'），或解析失败时返回 default_range
    """
    import re

    # 中文模式：最近/近/过去 + 数字 + 单位
    cn_patterns = [
        # "最近24小时" "近3天" "过去30分钟"
        r"(?:最近|近|过去)\s*(\d+)\s*(分钟|分|小时|天|周|个小时)",
        # "最近一天" "近三天" "过去一小时"
        r"(?:最近|近|过去)\s*([一二三四五六七八九十百]+)\s*(分钟|分|小时|天|周|个小时)",
    ]
    # 英文模式
    en_patterns = [
        r"(?:last|past|recent)\s*(\d+)\s*(minutes?|hours?|days?|d|h|m)",
    ]

    cn_num_map = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
        "十一": 11, "十二": 12, "二十四": 24, "三十": 30,
        "百": 100,
    }
    unit_map = {
        "分钟": "m", "分": "m", "小时": "h", "个小时": "h",
        "天": "d", "周": "w",
        "minutes": "m", "minute": "m", "m": "m",
        "hours": "h", "hour": "h", "h": "h",
        "days": "d", "day": "d", "d": "d",
    }

    query_lower = query.lower()

    # 尝试中文模式
    for pattern in cn_patterns:
        m = re.search(pattern, query_lower)
        if m:
            num_str = m.group(1)
            unit_str = m.group(2)
            # 解析数字
            if num_str.isdigit():
                num = int(num_str)
            else:
                num = cn_num_map.get(num_str, 0)
            unit = unit_map.get(unit_str, "")
            if num > 0 and unit:
                return f"{num}{unit}"

    # 尝试英文模式
    for pattern in en_patterns:
        m = re.search(pattern, query_lower)
        if m:
            num = int(m.group(1))
            unit_str = m.group(2)
            unit = unit_map.get(unit_str, "")
            if num > 0 and unit:
                return f"{num}{unit}"

    return default_range

# ====================================================================
#  共享核心逻辑（被流式 / 非流式端点复用）
# ====================================================================
async def _prepare_context(
    req: ChatRequest, auth: dict
) -> Dict:
    """准备 LLM 调用所需的完整上下文

    支持单技能和多技能联合分析模式：
    - 单技能: req.skill 或 req.skills 只有一个元素时，走原有逻辑
    - 多技能: req.skills 有多个元素时，逐个查询数据后合并为联合上下文

    Returns:
        {
            skill, model_cfg, messages, conversation_id, existing,
            history_msgs, query
        }
    """
    username = auth["username"]

    # 0. 从用户自然语言中解析时间范围（覆盖前端默认值）
    effective_time_range = _extract_time_from_query(req.query, req.time_range)
    if effective_time_range != req.time_range:
        print(f"[AIOPS] 自然语言时间解析: '{req.query}' -> {effective_time_range} (原始: {req.time_range})")
        req.time_range = effective_time_range

    # 统一处理：将 skill 和 skills 合并为 skill_names 列表
    skill_names = []
    if req.skills:
        skill_names = list(req.skills)
    elif req.skill:
        skill_names = [req.skill]

    # ---- 多技能联合分析模式 ----
    if len(skill_names) > 1:
        return await _prepare_multi_skill_context(req, auth, skill_names)

    # ---- 单技能模式（原有逻辑） ----
    # 1. 路由到技能
    skill = await skill_router.route(req.skill or (skill_names[0] if skill_names else None), req.query)
    if not skill:
        raise HTTPException(status_code=400, detail="没有找到可用的技能")

    # 2. 获取模型配置（提前到 ES 查询之前，供 LLM 条件提取使用）
    model_cfg = await model_scheduler.get_model(skill.model)
    if not model_cfg:
        raise HTTPException(status_code=500, detail="没有可用的模型配置")

    # 3. 根据数据源类型路由查询逻辑
    ds_type = (getattr(skill, "ds_type", None) or "es").lower()

    if ds_type == "prometheus":
        # Prometheus 数据源 → 查询监控指标
        stats = await _query_prometheus_stats(skill, req.time_range, req.start_time, req.end_time)
    else:
        # ES 数据源 → 原有 NL-to-ES 条件提取 + 聚合查询
        user_conditions = []
        if getattr(skill, "field_schema", None):
            try:
                fields = json.loads(skill.field_schema)
                user_conditions = await _extract_es_conditions(
                    req.query, fields, model_cfg
                )
            except (json.JSONDecodeError, TypeError):
                pass
        stats = await _query_es_stats(skill, req.time_range, user_conditions=user_conditions, start_time=req.start_time, end_time=req.end_time)

    # 5. 构建 Prompt —— 分层：system（角色+字段说明） + user（统计数据+问题）
    messages = await _build_messages(skill, req, stats)

    # 6. 加载历史上下文
    conversation_id, existing, history_msgs = await _load_history(req, auth, username)

    # 7. 组装多轮消息序列：system + 历史 + 当前 user prompt
    context_msgs = [messages[0]]  # system message 始终在最前
    context_msgs += [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in (history_msgs or [])[-MAX_CONTEXT_MESSAGES:]
    ]
    context_msgs += messages[1:]  # 当前 user message

    return {
        "skill": skill,
        "model_cfg": model_cfg,
        "messages": context_msgs,
        "conversation_id": conversation_id,
        "existing": existing,
        "query": req.query,
    }


# 报告模板映射：技能 prompt_template → 对应的结构化报告模板
# 当用户意图为"报告"时，自动切换到更专业的报告模板
REPORT_TEMPLATE_MAP = {
    # ES 技能
    "h3c_net_analysis.tpl": "network_report.tpl",
    "security_analysis.tpl": "security_report.tpl",
    "storage_analysis.tpl": "storage_report.tpl",
    "nginx_access_analysis.tpl": "application_report.tpl",
    "incident_analysis.tpl": "network_report.tpl",  # 综合故障→网络报告
    # Prometheus 技能
    "prometheus_analysis.tpl": "system_report.tpl",
}


def _detect_intent(query: str) -> str:
    """检测用户意图，决定响应风格。

    借鉴 SQLBot 的快速命令分类思路：
    - 'report'  → 用户明确要求生成分析报告/深度分析
    - 'qa'      → 用户在提问或对话，需要简洁直接的回答

    返回: 'report' 或 'qa'
    """
    # 报告类关键词 —— 用户明确要求结构化报告
    report_keywords = (
        "分析报告", "深度分析", "详细分析", "全面分析", "综合分析",
        "生成报告", "出一份报告", "写一份报告", "给我报告",
        "智能报告", "综合报告", "运维报告", "安全报告",
        "巡检报告", "健康报告", "态势报告",
        "root cause", "根因分析", "故障分析",
    )
    query_lower = query.strip().lower()
    for kw in report_keywords:
        if kw in query_lower:
            return "report"
    return "qa"


async def _build_messages(skill: Skill, req: ChatRequest, stats: dict) -> List[Dict]:
    """构建分层消息：system（角色 + 字段说明）+ user（数据上下文 + 用户问题）

    借鉴 SQLBot 的 SystemPromptMessage / HumanPromptMessage 分离模式：
    - system 定义 AI 的角色、能力和行为约束
    - user 提供数据上下文 + 用户的实际问题

    关键改进（v3.2）：
    - 不再强制所有回复都是"分析报告"格式
    - 通过意图检测区分：报告模式 vs 对话问答模式
    - 用户的问题是第一优先级，数据只是辅助上下文
    """
    intent = _detect_intent(req.query)

    # ---- 报告模板智能路由 ----
    # 当意图为 report 时，尝试使用对应的结构化报告模板（更专业、输出格式更规范）
    actual_template = skill.prompt_template
    if intent == "report":
        report_tpl = REPORT_TEMPLATE_MAP.get(skill.prompt_template)
        if report_tpl:
            actual_template = report_tpl
            print(f"[AIOPS] 报告模式: {skill.prompt_template} → {report_tpl}")

    # 获取 Prompt 模板（stats_text 通过 {{logs}} 占位符注入）
    prompt_template = await prompt_mgr.get_prompt(
        actual_template,
        time_range=_format_time_range(req.time_range, req.start_time, req.end_time),
        logs=stats["stats_text"][:STATS_MAX_CHARS],
    )

    # ---- 解析字段说明 ----
    field_info = ""
    if getattr(skill, "field_schema", None):
        try:
            fields = json.loads(skill.field_schema)
            if fields:
                field_lines = [
                    f"  - {f['name']} ({f.get('type','')}: {f.get('desc','')}"
                    + (f"，示例: {f['example']}" if f.get("example") else "") + ")"
                    for f in fields
                ]
                field_info = "\n".join(field_lines)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    is_agg = stats.get("mode") == "aggregation"
    is_prometheus = stats.get("mode") == "prometheus"

    # ---- system message：角色设定（根据意图调整） ----
    if intent == "report":
        system_content = (
            "你是 AIOps 智能运维平台的专业分析助手。\n\n"
            "## 当前任务\n"
            "用户要求生成一份结构化的运维分析报告。请基于提供的运维数据，"
            "给出准确、专业、结构化的深度分析。\n\n"
            "## 报告输出要求\n"
            "1. 使用 **Markdown** 格式输出（支持标题、表格、列表、代码块）\n"
            "2. 报告结构清晰：先给结论摘要，再逐项展开分析\n"
            "3. 如发现风险，明确标注风险等级（低/中/高/严重）\n"
            "4. 给出可操作的处置建议\n"
            "5. **所有时间均为东八区（UTC+8）时间**，直接使用即可\n"
        )
    else:
        system_content = (
            "你是 AIOps 智能运维平台的智能助手。\n\n"
            "## 核心原则\n"
            "1. **直接回答用户的问题** —— 用户问什么就答什么，简洁明了\n"
            "2. 根据问题复杂度自动调整回复长度：\n"
            "   - 简单问题（如'有没有异常'）→ 简短直接回答\n"
            "   - 具体查询（如'哪个设备报错最多'）→ 给出数据和简要说明\n"
            "   - 复杂问题 → 适当展开，但仍以回答问题为主\n"
            "3. 使用 **Markdown** 格式，但不要强制使用固定的报告模板\n"
            "4. 如发现明显风险，主动提醒，但不需要每次都输出完整报告\n"
            "5. **所有时间均为东八区（UTC+8）时间**\n\n"
            "## 重要约束\n"
            "- **不要** 在用户没有要求时自动生成完整的【分析报告】\n"
            "- **不要** 使用固定的报告模板（如 一、故障摘要 二、设备概览...）\n"
            "- **要** 像一个专业运维工程师一样自然对话\n"
            "- **要** 基于数据事实回答，不臆测未提供的信息\n"
        )

    # 数据说明（根据数据源类型区分）
    if is_prometheus:
        system_content += (
            "\n## 数据说明\n"
            "下方提供了 **Prometheus 监控指标数据**，包含系统资源使用率、服务健康状态等。\n"
            "- 每个指标按实例(instance)维度展示当前值、最小值、最大值、平均值\n"
            "- 可能包含活跃告警和采集目标健康状态\n"
            "请基于指标数据进行客观分析，关注异常值和阈值超标的实例。\n"
        )
    elif is_agg:
        system_content += (
            "\n## 数据说明\n"
            "下方提供了 **ES 聚合统计结果**，已完整覆盖用户要求的整个时间窗口。\n"
            "- 分布统计（terms）展示各字段的 Top 值及占比\n"
            "- 统计指标（stats）展示数值字段的 min/max/avg/sum\n"
            "- 百分位（P50/P95/P99）展示数值分布特征\n"
            "- 时间趋势展示各时段的文档数量变化\n"
            "请基于统计数据进行客观分析，不要臆测未提供的信息。\n"
        )
    if field_info:
        system_content += (
            f"\n## ES 索引字段说明\n"
            f"以下是日志中各字段的含义，请基于此理解数据内容：\n"
            f"{field_info}\n"
        )

    # CMDB 资产关联说明（始终追加，实际是否注入资产数据取决于数据中是否有 IP 匹配）
    system_content += (
        "\n## CMDB 资产关联\n"
        "如果下方数据中提供了 CMDB 资产关联表（IP→设备名称/区域/机房/负责人），请在分析中：\n"
        "1. **用设备名称替代纯 IP 地址**（如‘华南-深圳机房的Dell R740(192.168.1.100)’而非只写IP）\n"
        "2. **按区域/机房维度归纳问题**（如‘华南区域3台设备出现异常’）\n"
        "3. **提及负责人**以便明确责任人\n"
    )

    # ---- user message：用户问题优先 + 数据上下文 ----
    if is_prometheus:
        mode_label = "Prometheus 指标"
    elif is_agg:
        mode_label = "聚合统计"
    elif stats.get("mode") == "sample":
        mode_label = "样本日志"
    else:
        mode_label = "错误"

    data_source_label = "Prometheus 监控" if is_prometheus else "ES 查询"

    if intent == "report":
        # 报告模式：模板在前（包含报告结构指引），问题在后
        user_content = prompt_template
        user_content += (
            f"\n\n---\n"
            f"## 查询元数据\n"
            f"- 用户要求的时间范围：**{_format_time_range(req.time_range, req.start_time, req.end_time)}**\n"
            f"- 查询窗口（东八区）：**{stats.get('gte_cst', '?')} → {stats.get('lte_cst', '?')}**\n"
        )
        if not is_prometheus:
            user_content += f"- 窗口内总文档数：**{stats.get('total', 0)}** 条\n"
        user_content += (
            f"- 数据来源：**{data_source_label}**\n"
            f"- 数据模式：**{mode_label}**\n"
            f"- 用户的具体要求：**{req.query}**\n"
        )
        # 报告模式下也附加命令日志（如果有）
        command_text = stats.get("command_text", "")
        if command_text:
            user_content += f"\n{command_text[:COMMAND_MAX_CONTEXT]}\n"
    else:
        # 对话模式：问题在前（最重要），数据上下文在后
        user_content = f"## 我的问题\n{req.query}\n"
        user_content += (
            f"\n---\n"
            f"## 参考数据（来自{data_source_label}）\n"
            f"- 时间范围：{_format_time_range(req.time_range, req.start_time, req.end_time)}\n"
            f"- 查询窗口（东八区）：{stats.get('gte_cst', '?')} → {stats.get('lte_cst', '?')}\n"
        )
        if not is_prometheus:
            user_content += f"- 窗口内总文档数：{stats.get('total', 0)} 条\n"
        user_content += f"- 数据模式：{mode_label}\n\n"
        # 运维数据详情
        user_content += f"### 运维数据详情\n{stats['stats_text'][:STATS_MAX_CHARS]}\n"
        # 命令日志（独立截断预算，不与聚合统计争抢空间）
        command_text = stats.get("command_text", "")
        if command_text:
            user_content += f"\n{command_text[:COMMAND_MAX_CONTEXT]}\n"

    # ---- CMDB 资产关联注入 ----
    cmdb_context = await _enrich_with_cmdb(stats.get("stats_text", "") + stats.get("command_text", ""))
    if cmdb_context:
        user_content += cmdb_context

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


async def _prepare_multi_skill_context(
    req: ChatRequest, auth: dict, skill_names: List[str]
) -> Dict:
    """多技能联合分析：逐个技能查询数据，合并为统一上下文供 LLM 联合分析。

    流程：
    1. 逐个路由技能并查询数据（ES/Prometheus）
    2. 将各技能数据合并为带标签的统计文本
    3. 构建联合分析 Prompt，引导 LLM 做跨数据源关联分析
    4. 使用第一个技能的模型配置
    """
    username = auth["username"]
    print(f"[AIOPS] 多技能联合分析: {skill_names}")

    # 逐个技能查询数据
    skill_objs = []
    stats_list = []
    model_cfg = None

    for sn in skill_names:
        skill = await skill_router.route(sn, req.query)
        if not skill:
            print(f"[AIOPS] 技能 {sn} 未找到，跳过")
            continue

        if model_cfg is None:
            model_cfg = await model_scheduler.get_model(skill.model)

        ds_type = (getattr(skill, "ds_type", None) or "es").lower()
        if ds_type == "prometheus":
            stats = await _query_prometheus_stats(skill, req.time_range, req.start_time, req.end_time)
        else:
            user_conditions = []
            if getattr(skill, "field_schema", None):
                try:
                    fields = json.loads(skill.field_schema)
                    if model_cfg:
                        user_conditions = await _extract_es_conditions(
                            req.query, fields, model_cfg
                        )
                except (json.JSONDecodeError, TypeError):
                    pass
            stats = await _query_es_stats(skill, req.time_range, user_conditions=user_conditions, start_time=req.start_time, end_time=req.end_time)

        skill_objs.append(skill)
        stats_list.append({"skill": skill, "stats": stats})

    if not skill_objs:
        raise HTTPException(status_code=400, detail="没有找到可用的技能")
    if not model_cfg:
        raise HTTPException(status_code=500, detail="没有可用的模型配置")

    # 合并各技能的统计数据（带技能标签分隔）
    combined_parts = []
    for item in stats_list:
        s = item["skill"]
        st = item["stats"]
        ds_label = "Prometheus" if st.get("mode") == "prometheus" else "ES"
        combined_parts.append(
            f"\n{'='*60}\n"
            f"## 数据源: {s.display_name or s.skill_name} ({ds_label})\n"
            f"技能ID: {s.skill_name} | 索引: {getattr(s, 'index_pattern', 'N/A')}\n"
            f"时间窗口: {st.get('gte_cst', '?')} ~ {st.get('lte_cst', '?')}\n"
            f"总文档数: {st.get('total', 0)}\n"
            f"{'='*60}\n"
            f"{st['stats_text'][:STATS_MAX_CHARS // len(stats_list)]}"
        )
        # 命令日志也合并
        cmd_text = st.get("command_text", "")
        if cmd_text:
            combined_parts.append(
                cmd_text[:COMMAND_MAX_CONTEXT // len(stats_list)]
            )

    combined_stats_text = "\n".join(combined_parts)
    combined_stats = {
        "mode": "multi_skill",
        "total": sum(s["stats"].get("total", 0) for s in stats_list),
        "gte_cst": stats_list[0]["stats"].get("gte_cst", "?"),
        "lte_cst": stats_list[0]["stats"].get("lte_cst", "?"),
        "stats_text": combined_stats_text,
        "command_text": "",
        "skill_names": [s.skill_name for s in skill_objs],
    }

    # 构建联合分析 Prompt
    messages = await _build_multi_skill_messages(skill_objs, req, combined_stats)

    # 加载历史上下文
    conversation_id, existing, history_msgs = await _load_history(req, auth, username)

    context_msgs = [messages[0]]
    context_msgs += [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in (history_msgs or [])[-MAX_CONTEXT_MESSAGES:]
    ]
    context_msgs += messages[1:]

    # 返回时用第一个技能作为主技能（用于持久化记录）
    return {
        "skill": skill_objs[0],
        "model_cfg": model_cfg,
        "messages": context_msgs,
        "conversation_id": conversation_id,
        "existing": existing,
        "query": req.query,
    }


async def _build_multi_skill_messages(
    skills: List[Skill], req: ChatRequest, combined_stats: dict
) -> List[Dict]:
    """构建多技能联合分析的 Prompt"""
    skill_labels = "、".join(s.display_name or s.skill_name for s in skills)
    intent = _detect_intent(req.query)

    system_content = (
        "你是 AIOps 智能运维平台的专业分析助手，正在进行**多数据源联合分析**。\n\n"
        f"## 当前任务\n"
        f"用户要求基于以下技能数据进行联合分析：{skill_labels}\n"
        f"用户的具体要求：{req.query}\n\n"
    )

    if intent == "report":
        # 报告模式：使用结构化报告指引
        system_content += (
            "## 报告输出要求\n"
            "请严格按照以下结构输出专业报告：\n\n"
            "### 一、综合摘要\n"
            "以简洁段落概述整体运行状况，包含风险概览（🔴高/🟠中/🟡低/🟢正常）和综合健康评分（0-100分）。\n\n"
            "### 二、风险排行\n"
            "表格形式列出所有风险项，按等级排序：| 风险等级 | 风险类型 | 设备/来源 | AI分析 | 处置建议 |\n\n"
            "### 三、各数据源详细分析\n"
            "按数据源分节分析，每节末尾附 AI 点评。\n\n"
            "### 四、跨数据源关联分析\n"
            "重点发现单数据源无法发现的关联问题（如网络异常与设备告警的时间关联）。\n\n"
            "### 五、AI 总结与建议\n"
            "包含：风险总结、优先处理事项（表格：优先级/建议/时限）、趋势预测、健康评分（表格：维度/得分/说明）。\n\n"
            "## 其他要求\n"
            "- 使用 Markdown 格式\n"
            "- 所有时间均为东八区（UTC+8）时间\n"
            "- 基于实际数据，不编造数据，缺失数据标注“本周期内无相关数据”\n"
            "- 如提供了 CMDB 资产关联表，用设备名称替代纯 IP，按区域/机房维度归纳\n"
        )
    else:
        system_content += (
            "## 分析要求\n"
            "1. 使用 **Markdown** 格式输出结构化报告\n"
            "2. 先给出整体结论摘要\n"
            "3. 逐个数据源分析关键发现\n"
            "4. **重点进行跨数据源关联分析**，发现单数据源无法发现的关联问题\n"
            "5. 如发现风险，明确标注风险等级（低/中/高/严重）\n"
            "6. 给出可操作的处置建议\n"
            "7. **所有时间均为东八区（UTC+8）时间**\n"
            "8. 如果提供了 CMDB 资产关联表（IP→设备名称/区域/机房/负责人），请用设备名称替代纯 IP，按区域/机房维度归纳问题，并提及负责人\n"
        )

    user_content = (
        f"## 多技能联合分析请求\n"
        f"用户问题：{req.query}\n"
        f"涉及技能：{skill_labels}\n"
        f"时间范围：{_format_time_range(req.time_range, req.start_time, req.end_time)}\n"
        f"查询窗口：{combined_stats.get('gte_cst', '?')} ~ {combined_stats.get('lte_cst', '?')}\n"
        f"总文档数：{combined_stats.get('total', 0)}\n\n"
        f"---\n"
        f"### 各数据源详情\n"
        f"{combined_stats['stats_text'][:STATS_MAX_CHARS]}\n"
    )

    # ---- CMDB 资产关联注入 ----
    cmdb_context = await _enrich_with_cmdb(combined_stats.get("stats_text", ""))
    if cmdb_context:
        user_content += cmdb_context

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


async def _load_history(req: ChatRequest, auth: dict, username: str):
    """加载历史上下文（续接已有会话）"""
    if not req.conversation_id:
        return str(uuid.uuid4()), False, []

    async with async_session_factory() as session:
        result = await session.execute(
            select(Conversation).where(
                Conversation.conversation_id == req.conversation_id
            )
        )
        conv = result.scalar_one_or_none()
        if conv:
            if conv.user != username and auth["role"] != "admin":
                raise HTTPException(status_code=403, detail="无权操作该会话")
            return conv.conversation_id, True, conv.messages or []
    return str(uuid.uuid4()), False, []


async def _persist_conversation(
    ctx: Dict, response_text: str, risk_level: str = "medium"
) -> str:
    """持久化对话记录（流式结束后一次性写入，保持兼容现有 conversations 表）"""
    username = ctx.get("username", "unknown")
    req_query = ctx["query"]
    skill = ctx["skill"]
    conversation_id = ctx["conversation_id"]
    existing = ctx["existing"]

    summary = response_text[:200] + "..." if len(response_text) > 200 else response_text
    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    user_turn = {"role": "user", "content": req_query, "created_at": now_str}
    ai_turn = {
        "role": "assistant",
        "content": response_text,
        "risk_level": risk_level,
        "created_at": now_str,
    }

    try:
        async with async_session_factory() as session:
            if existing:
                result = await session.execute(
                    select(Conversation).where(
                        Conversation.conversation_id == conversation_id
                    )
                )
                conv = result.scalar_one_or_none()
                if conv:
                    msgs = list(conv.messages or [])
                    msgs.append(user_turn)
                    msgs.append(ai_turn)
                    conv.messages = msgs
                    conv.summary = summary
                    conv.risk_level = risk_level
                    conv.full_report = {"content": response_text}
            else:
                conv = Conversation(
                    conversation_id=conversation_id,
                    tenant=ctx.get("tenant", "ops"),
                    user=username,
                    skill=skill.skill_name,
                    title=(req_query.strip() or "AI对话")[:30],
                    query=req_query,
                    summary=summary,
                    risk_level=risk_level,
                    full_report={"content": response_text},
                    archived=0,
                    messages=[user_turn, ai_turn],
                )
                session.add(conv)
            await session.commit()
    except Exception as e:
        print(f"[AIOPS] 对话记录保存失败: {e}")

    return conversation_id


def _sse_frame(data: dict) -> str:
    """构建标准 SSE 帧：data:{json}\\n\\n"""
    return "data:" + orjson.dumps(data).decode() + "\n\n"


# ====================================================================
#  非流式端点（向后兼容）
# ====================================================================
@router.post("/chat")
async def chat(req: ChatRequest, auth=Depends(get_current_user)):
    """统一AI对话入口（非流式，保留向后兼容）"""
    ctx = await _prepare_context(req, auth)
    ctx["username"] = auth["username"]
    ctx["tenant"] = req.tenant
    model_cfg = ctx["model_cfg"]

    try:
        response = await llm_client.chat(
            messages=ctx["messages"],
            model=model_cfg["model_name"],
            temperature=0.7,
            api_base=model_cfg.get("api_base"),
            api_key=model_cfg.get("api_key"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"大模型调用失败（模型: {model_cfg['model_name']}）: {str(e)[:300]}",
        )

    conversation_id = await _persist_conversation(ctx, response)

    return ChatResponse(
        request_id=conversation_id,
        skill=ctx["skill"].skill_name,
        summary=response[:200] + "..." if len(response) > 200 else response,
        risk_level="medium",
        report={"content": response},
    )


# ====================================================================
#  流式端点（核心新增 —— 借鉴 SQLBot SSE 架构）
# ====================================================================
@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, auth=Depends(get_current_user)):
    """AI 对话流式端点 —— SSE Server-Sent Events

    返回 text/event-stream，分帧协议：
        data: {"type":"meta","conversation_id":"...","skill":"..."}\\n\\n
        data: {"type":"content","content":"逐段文本"}\\n\\n   ← 多帧
        data: {"type":"finish","risk_level":"medium"}\\n\\n
        data: {"type":"error","content":"错误信息"}\\n\\n      ← 异常时
    """
    username = auth["username"]

    # 准备上下文（路由/ES/Prompt/模型/历史）
    try:
        ctx = await _prepare_context(req, auth)
    except HTTPException as e:
        # 注意：Python 3 except 块退出后 e 会被删除，必须先捕获到局部变量
        err_msg = str(e.detail)
        async def _err():
            yield _sse_frame({"type": "error", "content": err_msg})
        return StreamingResponse(_err(), media_type="text/event-stream")
    except Exception as e:
        err_msg = f"上下文准备失败: {str(e)[:300]}"
        async def _err2():
            yield _sse_frame({"type": "error", "content": err_msg})
        return StreamingResponse(_err2(), media_type="text/event-stream")

    ctx["username"] = username
    ctx["tenant"] = req.tenant
    model_cfg = ctx["model_cfg"]
    conversation_id = ctx["conversation_id"]

    async def _stream_generator():
        """SSE 流式生成器 —— 借鉴 SQLBot LLMService.run_task 模式"""
        # 帧 1: meta（前端立即拿到 conversation_id 用于绑定会话）
        yield _sse_frame({
            "type": "meta",
            "conversation_id": conversation_id,
            "skill": ctx["skill"].skill_name,
        })

        full_text = ""
        try:
            async for chunk in llm_client.stream_chat(
                messages=ctx["messages"],
                model=model_cfg["model_name"],
                temperature=0.7,
                max_tokens=model_cfg.get("max_tokens", 16384),
                api_base=model_cfg.get("api_base"),
                api_key=model_cfg.get("api_key"),
            ):
                content = chunk.get("content", "")
                if content:
                    full_text += content
                    # 帧 N: content（逐 token 推送）
                    yield _sse_frame({"type": "content", "content": content})
        except Exception as e:
            # 借鉴 SQLBot _err() 模式：流式上报错误而非中断
            err_msg = f"大模型调用失败: {str(e)[:300]}"
            print(f"[AIOPS] 流式生成异常: {err_msg}")
            yield _sse_frame({"type": "error", "content": err_msg})
            return

        # 流式结束 —— 持久化完整对话（一次性写入）
        try:
            await _persist_conversation(ctx, full_text)
        except Exception as e:
            print(f"[AIOPS] 对话持久化异常(不影响响应): {e}")

        # 帧: finish（通知前端完成 + 返回元信息）
        yield _sse_frame({
            "type": "finish",
            "conversation_id": conversation_id,
            "risk_level": "medium",
        })

    return StreamingResponse(
        _stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，确保实时推送
            "Connection": "keep-alive",
        },
    )


# ====================================================================
#  Prometheus 指标查询 —— 从 Prometheus 采集监控数据用于 AI 分析
# ====================================================================
async def _query_prometheus_stats(skill: Skill, time_range: str, start_time: str = None, end_time: str = None) -> dict:
    """查询 Prometheus 数据源获取监控指标，格式化后返回给 LLM。

    根据技能的 query_config.promql_templates 执行 PromQL 查询，
    将结果格式化为 Markdown 表格供 LLM 分析。
    """
    tw = _compute_time_window(time_range, start_time, end_time)
    range_seconds = tw["range_seconds"]
    gte_cst = tw["gte_cst"]
    lte_cst = tw["lte_cst"]

    # 获取数据源配置
    ds_config = await _get_datasource_config(skill.datasource_id)
    client = get_prometheus_client(ds_config)

    duration_minutes = max(range_seconds // 60, 1)

    # 从 query_config 获取自定义 PromQL 查询
    query_config = skill.query_config or {}
    promql_templates = query_config.get("promql_templates", [])

    if promql_templates:
        # 有自定义 PromQL → 执行 range query 并格式化
        stats_text = await _query_prometheus_custom(
            client, promql_templates, duration_minutes
        )
    else:
        # 无自定义 PromQL → 使用默认全量采集
        metrics_data = await client.collect_system_metrics(duration_minutes)
        stats_text = _format_prometheus_metrics(metrics_data)

    print(f"[AIOPS] Prometheus查询: skill={skill.skill_name}, "
          f"duration={duration_minutes}min, "
          f"promql_count={len(promql_templates)}, "
          f"text_len={len(stats_text)}")

    return {
        "mode": "prometheus",
        "total": 0,
        "gte_cst": gte_cst,
        "lte_cst": lte_cst,
        "stats_text": stats_text,
        "command_text": "",
    }


async def _query_prometheus_custom(
    client, promql_templates: list, duration_minutes: int
) -> str:
    """执行自定义 PromQL 查询并格式化为 LLM 可读文本"""
    from datetime import datetime, timedelta

    end = datetime.now()
    start = end - timedelta(minutes=duration_minutes)
    start_str = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    step = "60s" if duration_minutes <= 60 else "300s"

    lines = []
    for tmpl in promql_templates:
        if isinstance(tmpl, str):
            promql = tmpl
            metric_name = tmpl[:40]
        else:
            promql = tmpl.get("promql", "")
            metric_name = tmpl.get("name", promql[:40])
        if not promql:
            continue

        try:
            data = await client.query_range(promql, start_str, end_str, step)
            results = data.get("result", [])
            if not results:
                lines.append(f"\n### {metric_name}\n无数据")
                continue

            lines.append(f"\n### {metric_name}")
            lines.append("| 实例 | 当前值 | 最小值 | 最大值 | 平均值 |")
            lines.append("|------|------|------|------|------|")

            for series in results[:20]:
                labels = series.get("metric", {})
                values = series.get("values", [])
                if not values:
                    continue
                nums = [float(v[1]) for v in values if v[1] != "NaN"]
                if not nums:
                    continue
                instance = labels.get("instance", labels.get("job", "unknown"))
                latest = round(nums[-1], 2)
                min_v = round(min(nums), 2)
                max_v = round(max(nums), 2)
                avg_v = round(sum(nums) / len(nums), 2)
                lines.append(f"| {instance} | {latest} | {min_v} | {max_v} | {avg_v} |")

        except Exception as e:
            lines.append(f"\n### {metric_name}\n查询失败: {str(e)[:100]}")

    # 补充获取活跃告警
    try:
        alerts = await client.get_alerts()
        if alerts:
            lines.append("\n### 活跃告警")
            lines.append("| 告警名 | 严重级 | 实例 | 状态 | 摘要 |")
            lines.append("|------|------|------|------|------|")
            for a in alerts[:15]:
                labels = a.get("labels", {})
                annotations = a.get("annotations", {})
                lines.append(
                    f"| {labels.get('alertname', '')} "
                    f"| {labels.get('severity', '')} "
                    f"| {labels.get('instance', '')} "
                    f"| {a.get('state', '')} "
                    f"| {(annotations.get('summary', '') or annotations.get('description', ''))[:80]} |"
                )
    except Exception:
        pass

    # 获取 targets 健康状态
    try:
        targets = await client.get_targets()
        if targets:
            up_count = sum(1 for t in targets if t.get("health") == "up")
            down_count = sum(1 for t in targets if t.get("health") != "up")
            lines.append(f"\n### 采集目标状态")
            lines.append(f"总计: {len(targets)}个目标，{up_count}个健康，{down_count}个异常")
            if down_count > 0:
                lines.append("| 实例 | Job | 状态 | 错误 |")
                lines.append("|------|------|------|------|")
                for t in targets:
                    if t.get("health") != "up":
                        lines.append(
                            f"| {t.get('labels', {}).get('instance', '')} "
                            f"| {t.get('labels', {}).get('job', '')} "
                            f"| {t.get('health', '')} "
                            f"| {(t.get('lastError', '') or '')[:80]} |"
                        )
    except Exception:
        pass

    return "\n".join(lines) if lines else "（未获取到 Prometheus 指标数据）"


def _format_prometheus_metrics(metrics_data: dict) -> str:
    """将 collect_system_metrics 的结果格式化为 LLM 可读文本"""
    lines = []

    metric_names = {
        "cpu_usage": "CPU 使用率 (%)",
        "memory_usage": "内存使用率 (%)",
        "disk_usage": "磁盘使用率 (%)",
        "load_average": "系统负载 (Load5)",
        "network_receive": "网络接收 (bytes/s)",
        "network_transmit": "网络发送 (bytes/s)",
        "up_status": "服务存活状态",
    }

    for key, title in metric_names.items():
        data = metrics_data.get(key)
        if not data:
            continue
        if isinstance(data, dict) and "error" in data:
            lines.append(f"\n### {title}\n查询失败: {data['error'][:100]}")
            continue
        if isinstance(data, list) and data:
            lines.append(f"\n### {title}")
            lines.append("| 实例 | 当前值 | 最小值 | 最大值 | 平均值 |")
            lines.append("|------|------|------|------|------|")
            for item in data[:20]:
                labels = item.get("labels", {})
                instance = labels.get("instance", labels.get("job", "unknown"))
                lines.append(
                    f"| {instance} "
                    f"| {item.get('latest', 'N/A')} "
                    f"| {item.get('min', 'N/A')} "
                    f"| {item.get('max', 'N/A')} "
                    f"| {item.get('avg', 'N/A')} |"
                )

    # 活跃告警
    alerts = metrics_data.get("active_alerts", [])
    if alerts:
        lines.append("\n### 活跃告警")
        lines.append("| 告警名 | 严重级 | 实例 | 状态 | 摘要 |")
        lines.append("|------|------|------|------|------|")
        for a in alerts:
            lines.append(
                f"| {a.get('alertname', '')} "
                f"| {a.get('severity', '')} "
                f"| {a.get('instance', '')} "
                f"| {a.get('state', '')} "
                f"| {a.get('summary', '')[:80]} |"
            )

    # 采集目标
    targets = metrics_data.get("targets", [])
    if targets:
        up_count = sum(1 for t in targets if t.get("health") == "up")
        down_count = sum(1 for t in targets if t.get("health") != "up")
        lines.append(f"\n### 采集目标状态")
        lines.append(f"总计: {len(targets)}个目标，{up_count}个健康，{down_count}个异常")
        if down_count > 0:
            for t in targets:
                if t.get("health") != "up":
                    lines.append(
                        f"  - {t.get('instance', '')} ({t.get('job', '')}): "
                        f"{t.get('health', '')} - {(t.get('lastError', '') or '')[:60]}"
                    )

    return "\n".join(lines) if lines else "（未获取到 Prometheus 指标数据）"


async def _get_datasource_config(datasource_id: int) -> dict:
    """获取数据源连接配置"""
    if not datasource_id:
        return {}
    async with async_session_factory() as session:
        result = await session.execute(
            select(Datasource).where(Datasource.id == datasource_id)
        )
        ds = result.scalar_one_or_none()
    if not ds:
        return {}
    return {
        "host": ds.host,
        "port": ds.port,
        "username": ds.username or "",
        "password": ds.password or "",
        "extra_config": ds.extra_config or {},
    }


# ====================================================================
#  ES 聚合查询 —— 用 size:0 + aggregations 覆盖完整时间窗口
# ====================================================================
def _parse_time_range(time_range: str) -> int:
    """解析时间范围为秒数"""
    if not time_range:
        return 1800
    unit = time_range[-1]
    value_str = time_range[:-1]
    if not value_str.isdigit():
        return 1800
    value = int(value_str)
    if unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    elif unit == "d":
        return value * 86400
    return 1800  # 默认30分钟


def _parse_datetime_flexible(raw: str) -> datetime:
    """灵活解析多种日期时间格式，返回带时区的 datetime（CST）。"""
    if not raw:
        raise ValueError("empty")
    raw = raw.strip()
    # 尝试 ISO 8601（含 T 分隔）
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=CST)
        except ValueError:
            continue
    raise ValueError(f"无法解析日期时间: {raw}")


def _compute_time_window(time_range: str, start_time: str = None, end_time: str = None) -> dict:
    """计算时间窗口，返回 UTC 时间字符串和 CST 显示字符串。

    优先使用 start_time/end_time（自定义范围），
    否则使用 time_range 相对时间（如 30m、24h、7d）。

    返回 dict:
      gte_str, lte_str: UTC ISO 格式（用于 ES 查询）
      gte_cst, lte_cst: CST 可读格式（用于 Prompt 显示）
      range_seconds: 总秒数（用于聚合 bucket 计算）
    """
    now_utc = datetime.now(timezone.utc)

    if start_time and end_time:
        gte_utc = _parse_datetime_flexible(start_time).astimezone(timezone.utc)
        lte_utc = _parse_datetime_flexible(end_time).astimezone(timezone.utc)
        range_seconds = max(int((lte_utc - gte_utc).total_seconds()), 60)
    else:
        range_seconds = _parse_time_range(time_range)
        gte_utc = now_utc - timedelta(seconds=range_seconds)
        lte_utc = now_utc

    return {
        "gte_str": gte_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "lte_str": lte_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "gte_cst": gte_utc.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S"),
        "lte_cst": lte_utc.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S"),
        "range_seconds": range_seconds,
    }


def _build_single_es_condition(cond: dict, es_meta: dict) -> dict:
    """将单个结构化过滤条件转为 ES query 子句。

    cond = {"field":"status", "operator":"gte", "value":500}

    支持的操作符（根据 ES 字段类型自动适配）：
      eq / neq / in / contains / not_contains / gt / gte / lt / lte / cidr

    对于 text 类型字段，自动追加 .keyword 子字段做精确匹配。
    """
    field = str(cond.get("field", "")).strip()
    op = str(cond.get("operator", "eq")).strip()
    val = cond.get("value")
    if not field or val is None or val == "":
        return None

    es_types = (es_meta or {}).get("types", {})
    has_keyword = (es_meta or {}).get("has_keyword", set())
    es_type = es_types.get(field, "keyword")

    # text 字段需要用 .keyword 子字段做精确匹配，否则 ES 报 fielddata 错误
    use_keyword_sub = es_type == "text" and field in has_keyword
    term_field = f"{field}.keyword" if use_keyword_sub else field

    # 数值类型自动转换
    if es_type in ("integer", "long", "float", "double"):
        try:
            if isinstance(val, str):
                val = float(val) if "." in val else int(val)
        except (ValueError, TypeError):
            pass

    if op in ("eq", "==", "is"):
        return {"term": {term_field: {"value": val}}}
    elif op in ("neq", "!=", "isnot"):
        return {"bool": {"must_not": [{"term": {term_field: {"value": val}}}]}}
    elif op == "in":
        vals = val if isinstance(val, list) else [val]
        return {"terms": {term_field: vals}}
    elif op == "contains":
        return {"wildcard": {term_field: {"value": f"*{val}*"}}}
    elif op == "not_contains":
        return {"bool": {"must_not": [{"wildcard": {term_field: {"value": f"*{val}*"}}}]}}
    elif op in ("gt", "gte", "lt", "lte"):
        return {"range": {field: {op: val}}}
    elif op == "cidr":
        # ES 对 ip 类型原生支持 CIDR 表示法
        return {"term": {field: val}}
    else:
        return {"term": {term_field: {"value": val}}}


def _build_query_filters(query_filter_str: str, es_meta: dict, skip_fields: set = None) -> list:
    """解析技能的 query_filter JSON 并转换为 ES bool filter 子句列表（智能逻辑）。

    query_filter 格式：
        {
            "conditions": [
                {"field":"src_ip","operator":"neq","value":"192.168.167.242"},
                {"field":"module","operator":"eq","value":"SNMP"},
                {"field":"module","operator":"eq","value":"NETCONF"}
            ]
        }

    智能逻辑规则（无需用户手动选 AND/OR）：
      - 排除条件 (neq / not_contains) → 全部 AND（must_not，排除所有指定值）
      - 包含条件 (eq / contains / in 等) 同字段 → OR（匹配任一值）
      - 不同字段之间 → AND

    参数：
      skip_fields: 跳过指定字段的条件（用于命令日志查询时跳过 module/event_name）

    返回单个 bool 子句列表，可拼入外层 bool.filter 数组。
    """
    if not query_filter_str:
        return []

    try:
        config = json.loads(query_filter_str)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(config, dict):
        return []

    conditions = config.get("conditions", [])
    if not isinstance(conditions, list) or len(conditions) == 0:
        return []

    es_types = (es_meta or {}).get("types", {})
    has_keyword = (es_meta or {}).get("has_keyword", set())

    # 分组：排除条件 vs 包含条件
    exclusion_clauses = []   # 放入 must_not
    inclusion_by_field = {}  # field -> [clause, ...] 同字段多值用 OR

    for cond in conditions:
        if not isinstance(cond, dict):
            continue
        field = str(cond.get("field", "")).strip()
        op = str(cond.get("operator", "eq")).strip()
        val = cond.get("value")
        if not field or val is None or val == "":
            continue
        # 跳过指定字段（命令日志查询时跳过 module/event_name）
        if skip_fields and field in skip_fields:
            continue

        # 确定 term 字段名（text 类型需要 .keyword）
        es_type = es_types.get(field, "keyword")
        use_keyword_sub = es_type == "text" and field in has_keyword
        term_field = f"{field}.keyword" if use_keyword_sub else field

        # 数值类型自动转换
        if es_type in ("integer", "long", "float", "double"):
            try:
                if isinstance(val, str):
                    val = float(val) if "." in val else int(val)
            except (ValueError, TypeError):
                pass

        if op in ("neq", "!=", "isnot"):
            # 排除：生成正向匹配子句，放入 must_not
            exclusion_clauses.append({"term": {term_field: {"value": val}}})
        elif op == "not_contains":
            exclusion_clauses.append({"wildcard": {term_field: {"value": f"*{val}*"}}})
        elif op in ("eq", "==", "is"):
            inclusion_by_field.setdefault(field, []).append(
                {"term": {term_field: {"value": val}}})
        elif op == "in":
            vals = val if isinstance(val, list) else [val]
            inclusion_by_field.setdefault(field, []).append(
                {"terms": {term_field: vals}})
        elif op == "contains":
            inclusion_by_field.setdefault(field, []).append(
                {"wildcard": {term_field: {"value": f"*{val}*"}}})
        elif op in ("gt", "gte", "lt", "lte"):
            inclusion_by_field.setdefault(field, []).append(
                {"range": {field: {op: val}}})
        elif op == "cidr":
            inclusion_by_field.setdefault(field, []).append(
                {"term": {field: val}})
        else:
            inclusion_by_field.setdefault(field, []).append(
                {"term": {term_field: {"value": val}}})

    # 构建最终 bool 子句
    combined_bool = {}

    # 排除条件 → must_not（全部 AND）
    if exclusion_clauses:
        combined_bool["must_not"] = exclusion_clauses

    # 包含条件 → filter（同字段 OR，不同字段 AND）
    inclusion_filters = []
    for field, clauses in inclusion_by_field.items():
        if len(clauses) == 1:
            inclusion_filters.append(clauses[0])
        else:
            # 同字段多个值 → OR
            inclusion_filters.append({
                "bool": {"should": clauses, "minimum_should_match": 1}
            })
    if inclusion_filters:
        combined_bool["filter"] = inclusion_filters

    if not combined_bool:
        return []

    # 打印可读的过滤逻辑
    desc_parts = []
    if exclusion_clauses:
        desc_parts.append(f"排除{len(exclusion_clauses)}项")
    if inclusion_filters:
        desc_parts.append(f"包含{len(inclusion_filters)}组")
    print(f"[AIOPS] 智能过滤: {', '.join(desc_parts)} → "
          f"must_not={len(exclusion_clauses)}, "
          f"inclusion_groups={len(inclusion_filters)}")

    return [{"bool": combined_bool}]


def _detect_ts_field(fields: list, es_meta: dict = None) -> str:
    """从字段配置 + ES 实际映射中检测可用的日期字段。

    优先级：
    1. schema 中声明为 date 且 ES 中也是 date 的字段（最可靠）
    2. ES 中 @timestamp 为 date（最常见，绝大多数索引都有）
    3. @timestamp（安全默认值）

    关键场景：h3c-net-logs 的 field_schema 把 timestamp 标为 date，
    但 ES 中 timestamp 实际是 text、@timestamp 才是 date。
    若盲信 schema 会用 text 字段做 range 查询，导致返回 0 条结果。

    重要：当 es_meta 为空（get_mapping 调用失败/超时）时，
    绝不回退到 schema 声明的 date 字段（可能是 text），直接用 @timestamp。
    """
    es_types = (es_meta or {}).get("types", {})

    # es_meta 为空时（ES 映射获取失败），直接用 @timestamp 安全默认值
    # 不信任 schema 声明的 date 字段，因为它在 ES 中可能是 text
    if not es_types:
        return "@timestamp"

    # 1. schema date field that is also date in ES
    for f in fields:
        if f.get("type") == "date":
            name = f.get("name", "")
            if name and es_types.get(name) == "date":
                return name

    # 2. @timestamp is date in ES (most common fallback)
    if es_types.get("@timestamp") == "date":
        return "@timestamp"

    # 3. @timestamp (safe default — never use schema date field blindly)
    return "@timestamp"


def _build_es_aggregations(fields: list, range_seconds: int, es_meta: dict) -> dict:
    """根据技能字段配置 + ES 实际映射构建聚合查询 DSL。

    es_meta = {"types": {field_name: es_type}, "has_keyword": set(field_names)}

    聚合策略（完整覆盖整个查询时间窗口，不受 size 截断影响）：
    - keyword/ip 类型      → terms 聚合（值分布 Top N）
    - integer/long/float   → stats + percentiles 聚合（统计指标）
    - text + 有.keyword    → terms 聚合 on .keyword 子字段
    - text + 无.keyword    → 跳过（无法聚合）
    - date 类型            → date_histogram（时间趋势分桶）
    - 特殊：responsetime + request → 慢请求过滤聚合（哪个接口慢）

    关键改进：不再盲信 field_schema 中的类型声明，而是以 ES 实际映射为准，
    避免因 schema 与真实映射不一致导致 fielddata 错误。
    """
    aggs = {}
    es_types = es_meta.get("types", {})
    has_keyword = es_meta.get("has_keyword", set())

    ts_field = _detect_ts_field(fields, es_meta)

    # 时间趋势分桶：目标 AGGS_TIME_BUCKETS 个桶，每桶至少 60 秒
    interval_sec = max(range_seconds // AGGS_TIME_BUCKETS, 60)
    aggs["time_trend"] = {
        "date_histogram": {
            "field": ts_field,
            "fixed_interval": f"{interval_sec}s",
            "format": "HH:mm",
            "min_doc_count": 0,
        }
    }

    # 不适合做分布聚合的字段（文本太长/无区分度）
    skip_fields = {"message", "referer", "http_user_agent", "upstreamaddr"}

    for f in fields:
        name = f.get("name", "")
        if not name or name in skip_fields:
            continue

        # 优先使用 ES 实际映射类型，回退到 field_schema 声明类型
        actual_type = es_types.get(name, f.get("type", ""))

        if actual_type in ("date", "geo_point", "object", "nested"):
            continue

        if actual_type in ("keyword", "ip"):
            aggs[f"dist_{name}"] = {
                "terms": {"field": name, "size": AGGS_TERMS_SIZE}
            }
        elif actual_type in ("integer", "long", "float", "double"):
            aggs[f"stats_{name}"] = {"stats": {"field": name}}
            aggs[f"pct_{name}"] = {
                "percentiles": {"field": name, "percents": [50, 95, 99]}
            }
        elif actual_type == "text":
            # text 字段必须通过 .keyword 子字段做 terms 聚合
            if name in has_keyword:
                aggs[f"dist_{name}"] = {
                    "terms": {"field": f"{name}.keyword", "size": AGGS_TERMS_SIZE}
                }
            # 无 .keyword 子字段的 text 字段：跳过（ES 会报 fielddata 错误）

    # 特殊处理：慢请求分析（nginx / web 类日志）
    rt_type = es_types.get("responsetime", "")
    if rt_type in ("float", "double", "long", "integer"):
        req_field = "request.keyword" if "request" in has_keyword else None
        slow_agg = {"filter": {"range": {"responsetime": {"gte": 1.0}}}}
        if req_field:
            slow_agg["aggs"] = {
                "top_endpoints": {
                    "terms": {"field": req_field, "size": 10},
                    "aggs": {"avg_rt": {"avg": {"field": "responsetime"}}},
                }
            }
        aggs["slow_requests"] = slow_agg

    return aggs


def _format_stats_for_llm(aggs_result: dict, fields: list) -> str:
    """将 ES 聚合结果格式化为 LLM 可读的 Markdown 统计摘要"""
    lines = []
    field_desc = {f.get("name", ""): f.get("desc", "") for f in fields}

    for key, val in aggs_result.items():
        if key == "time_trend":
            buckets = val.get("buckets", [])
            if buckets:
                lines.append("\n### 时间趋势（每桶文档数）")
                trend_parts = [f"{b['key_as_string']}={b['doc_count']}" for b in buckets]
                # 每行最多 6 个桶，避免过长
                for i in range(0, len(trend_parts), 6):
                    lines.append("  ".join(trend_parts[i:i + 6]))

        elif key.startswith("dist_"):
            field_name = key[5:]
            desc = field_desc.get(field_name, field_name)
            buckets = val.get("buckets", [])
            if buckets:
                lines.append(f"\n### {desc}（{field_name}）分布")
                lines.append("| 值 | 数量 | 占比 |")
                lines.append("|------|------|------|")
                bucket_total = sum(b["doc_count"] for b in buckets)
                for b in buckets:
                    pct = f"{b['doc_count'] / bucket_total * 100:.1f}%" if bucket_total else "0%"
                    lines.append(f"| {b['key']} | {b['doc_count']} | {pct} |")
                other = val.get("sum_other_doc_count", 0)
                if other > 0:
                    lines.append(f"| (其他) | {other} | - |")

        elif key.startswith("stats_"):
            field_name = key[6:]
            desc = field_desc.get(field_name, field_name)
            lines.append(f"\n### {desc}（{field_name}）统计指标")
            avg_v = val.get("avg")
            lines.append(f"- 最小值: {val.get('min', 'N/A')}")
            lines.append(f"- 最大值: {val.get('max', 'N/A')}")
            lines.append(f"- 平均值: {avg_v:.4f}" if avg_v is not None else "- 平均值: N/A")
            lines.append(f"- 总和: {val.get('sum', 'N/A')}")
            lines.append(f"- 样本数: {val.get('count', 0)}")

        elif key.startswith("pct_"):
            field_name = key[4:]
            desc = field_desc.get(field_name, field_name)
            values = val.get("values", {})
            if values:
                lines.append(f"\n### {desc}（{field_name}）百分位")
                for p in ["50.0", "95.0", "99.0"]:
                    if p in values and values[p] is not None:
                        lines.append(f"- P{int(float(p))}: {values[p]:.4f}")

        elif key == "slow_requests":
            doc_count = val.get("doc_count", 0)
            lines.append(f"\n### 慢请求分析（响应时间 ≥ 1 秒）")
            lines.append(f"- 慢请求总数: **{doc_count}**")
            sub = val.get("top_endpoints", {})
            sub_buckets = sub.get("buckets", []) if isinstance(sub, dict) else []
            if sub_buckets:
                lines.append("\n| 接口路径 | 慢请求次数 | 平均响应时间(秒) |")
                lines.append("|------|------|------|")
                for b in sub_buckets:
                    avg_rt = b.get("avg_rt", {}).get("value", 0) or 0
                    path = str(b["key"])[:80]
                    lines.append(f"| {path} | {b['doc_count']} | {avg_rt:.3f} |")

    return "\n".join(lines) if lines else "（无聚合数据）"


def _format_sample_logs_for_llm(logs: list, fields: list) -> str:
    """将最近的原始日志样本格式化为 LLM 可读的紧凑摘要。

    聚合模式下，除了统计概览外，额外提供最新的若干条原始日志，
    让 LLM 能看到具体的命令文本、事件详情等。

    解决场景：用户问"最近1小时有没有做配置变更"，但聚合统计只给出
    terms 分布和计数，无法展示具体的 NAT 配置命令内容。补充样本日志
    后，LLM 即可引用具体的 command 文本回答此类问题。
    """
    if not logs:
        return ""

    # 排除超长/无区分度的字段
    skip_fields = {"message", "referer", "http_user_agent", "upstreamaddr"}
    field_names = [
        f.get("name", "") for f in fields
        if f.get("name", "") and f.get("name", "") not in skip_fields
    ]

    lines = []
    lines.append("\n### 最近样本日志（原始记录，最新在前）")
    lines.append("以下是最新的若干条原始日志，可用于查看具体命令、配置变更等细节：")

    for i, log in enumerate(logs, 1):
        if not isinstance(log, dict):
            continue
        parts = []
        for fname in field_names:
            val = log.get(fname)
            if val is None or val == "":
                continue
            val_str = str(val)
            if len(val_str) > SAMPLE_FIELD_MAX_LEN:
                val_str = val_str[:SAMPLE_FIELD_MAX_LEN] + "..."
            parts.append(f"{fname}: {val_str}")
        if parts:
            lines.append(f"  [{i}] " + " | ".join(parts))

    return "\n".join(lines)


def _format_command_logs_for_llm(logs: list, total_count: int, filter_label: str = "") -> str:
    """将命令执行日志格式化为 LLM 可读的紧凑列表（专项查询结果）。

    通用样本日志仅取最新若干条且按时间混排，配置变更命令可能被其他类型
    日志淹没。本函数单独输出命令执行记录，确保用户询问"配置变更/最近操作"
    时，LLM 能完整、准确地引用每一条命令内容。

    专项查询条件（匹配实际运维查询）：
      must  = exists:command + module.keyword=SHELL + event_name.keyword=SHELL_CMD
      filter= 时间范围
    """
    if not logs:
        return ""

    lines = []
    lines.append(f"\n### 命令执行记录（专项查询，最新在前）{filter_label}")
    if total_count > len(logs):
        lines.append(f"时间窗口内共匹配 {total_count} 条命令记录，以下展示最近 {len(logs)} 条：")
    else:
        lines.append(f"时间窗口内共匹配 {len(logs)} 条命令记录：")

    for i, log in enumerate(logs, 1):
        if not isinstance(log, dict):
            continue
        command = log.get("command")
        if command is None or str(command).strip() == "":
            continue
        cmd_str = str(command)
        if len(cmd_str) > COMMAND_MAX_LEN:
            cmd_str = cmd_str[:COMMAND_MAX_LEN] + "..."
        parts = [f"命令={cmd_str}"]
        ts = log.get("@timestamp") or log.get("timestamp") or ""
        if ts:
            parts.insert(0, f"时间={ts}")
        # 设备信息：同时展示 hostname 和 device_ip（两者含义不同，不能用 or 丢弃）
        hostname = log.get("hostname") or ""
        device_ip = log.get("device_ip") or ""
        if hostname:
            parts.append(f"设备名={hostname}")
        if device_ip:
            parts.append(f"设备IP={device_ip}")
        # 用户信息：同时展示 user 和 src_ip
        user_name = log.get("user") or ""
        src_ip = log.get("src_ip") or ""
        if user_name:
            parts.append(f"用户={user_name}")
        if src_ip:
            parts.append(f"来源IP={src_ip}")
        lines.append(f"  [{i}] " + " | ".join(parts))

    return "\n".join(lines)


# ====================================================================
#  语义理解：自然语言 → ES 查询条件（借鉴 SQLBot 的 NL-to-SQL 思路）
# ====================================================================
_CONDITION_EXTRACT_SYSTEM = """You are an Elasticsearch query condition extractor for an AIOps platform.

Task: Extract **explicit** filter conditions from the user's natural language question.

## Available Fields
{field_desc}

## Rules
1. Only extract conditions the user **explicitly states** (e.g. specific IP, username, command keyword).
2. Do NOT invent conditions the user did not mention.
3. Time range is handled separately — do NOT extract time-related conditions.
4. Return a JSON array. If no conditions found, return `[]`.

## Supported Operators
- eq: equals (for exact value match)
- neq: not equals
- contains: partial text match
- not_contains: text does not contain
- gt / gte / lt / lte: numeric comparisons
- in: value is one of a list

## Output Format (strict JSON, no explanation)
```json
[
  {{"field": "field_name", "operator": "op", "value": "val"}}
]
```

## Examples
Q: "设备ip是192.168.37.3执行过什么命令"  A: [{{"field":"device_ip","operator":"eq","value":"192.168.37.3"}}]
Q: "jgswy用户最近做了什么操作"     A: [{{"field":"user","operator":"eq","value":"jgswy"}}]
Q: "有没有执行过nat相关命令"       A: [{{"field":"command","operator":"contains","value":"nat"}}]
Q: "查看severity大于5的事件"       A: [{{"field":"severity","operator":"gt","value":5}}]
Q: "最近有什么异常"               A: []
Q: "分析下网络设备的运行状态"       A: []
"""


async def _extract_es_conditions(
    query: str, field_schema: list, model_cfg: dict
) -> list:
    """借鉴 SQLBot 的 NL-to-SQL 思路：用 LLM 将自然语言转为 ES 查询条件。

    流程（类比 SQLBot）：
      SQLBot: user question → LLM → SQL   → execute → results
      AIOps:  user question → LLM → ES条件 → execute → results

    通过将 field_schema（字段名、类型、描述）注入 system prompt，
    让 LLM 理解数据结构，从用户问题中提取出精准的过滤条件。

    Args:
        query: 用户的自然语言问题
        field_schema: 技能的字段配置列表 [{name, type, desc, example}]
        model_cfg: 模型配置（api_base, api_key, model_name）

    Returns:
        [{"field": "device_ip", "operator": "eq", "value": "192.168.37.3"}, ...]
        解析失败或无条件时返回 []
    """
    if not field_schema or not query.strip():
        return []

    # 构建字段说明（注入 system prompt，让 LLM 理解数据 schema）
    field_lines = []
    for f in field_schema:
        name = f.get("name", "")
        ftype = f.get("type", "")
        desc = f.get("desc", "")
        example = f.get("example", "")
        line = f"- {name} ({ftype}): {desc}"
        if example:
            line += f"  Example: {example}"
        field_lines.append(line)
    field_desc = "\n".join(field_lines)

    system_prompt = _CONDITION_EXTRACT_SYSTEM.format(field_desc=field_desc)

    try:
        response = await llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            model=model_cfg.get("model_name"),
            temperature=0.1,   # 低温度保证确定性输出
            max_tokens=512,    # 条件 JSON 通常很短
            api_base=model_cfg.get("api_base"),
            api_key=model_cfg.get("api_key"),
        )

        # 解析 JSON —— LLM 可能返回 ```json ... ``` 包裹
        text = response.strip()
        if "```" in text:
            # 提取 ``` 内的内容
            import re
            m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
            if m:
                text = m.group(1)
        conditions = json.loads(text)
        if not isinstance(conditions, list):
            return []

        # 验证每个条件的格式
        valid = []
        valid_fields = {f.get("name", "") for f in field_schema}
        for c in conditions:
            if (isinstance(c, dict)
                    and c.get("field") in valid_fields
                    and c.get("operator")
                    and c.get("value") is not None):
                valid.append(c)

        if valid:
            print(f"[AIOPS] LLM语义提取: '{query}' -> {json.dumps(valid, ensure_ascii=False)}")
        return valid

    except Exception as e:
        print(f"[AIOPS] LLM条件提取失败({e})，跳过预过滤")
        return []


async def _query_es_stats(skill: Skill, time_range: str, user_conditions: list = None, start_time: str = None, end_time: str = None) -> dict:
    """运行 ES 聚合查询，返回覆盖完整时间窗口的统计摘要。

    借鉴 SQLBot 的"查询执行"阶段：上一步 LLM 已将自然语言转为 ES 条件，
    本函数将这些条件应用到实际 ES 查询中，确保返回的数据精准匹配用户意图。

    user_conditions 来源：_extract_es_conditions() 的 LLM 提取结果。

    对于有 field_schema 配置的技能 → 聚合模式（推荐）
    对于无 field_schema 的技能     → 回退到少量样本日志
    """
    tw = _compute_time_window(time_range, start_time, end_time)
    gte_str = tw["gte_str"]
    lte_str = tw["lte_str"]
    gte_cst = tw["gte_cst"]
    lte_cst = tw["lte_cst"]
    range_seconds = tw["range_seconds"]

    # 解析字段配置
    fields = []
    if getattr(skill, "field_schema", None):
        try:
            fields = json.loads(skill.field_schema)
        except (json.JSONDecodeError, TypeError):
            pass

    # 获取ES实际字段类型映射（用于检测正确的日期字段 + 构建聚合）
    es_meta = await es_client.get_field_types(skill.index_pattern)
    if not es_meta.get("types"):
        print(f"[AIOPS] 警告: ES映射获取失败(index={skill.index_pattern})，"
              f"使用安全默认 @timestamp 作为时间字段")

    ts_field = _detect_ts_field(fields, es_meta) if fields else "@timestamp"
    range_filter = {"range": {ts_field: {"gte": gte_str, "lte": lte_str}}}

    # === 构建完整 filter：时间范围 + 技能级自定义查询条件 + LLM提取的用户条件 ===
    all_filters = [range_filter]
    custom_filters = _build_query_filters(getattr(skill, "query_filter", None), es_meta)
    if custom_filters:
        all_filters.extend(custom_filters)
        print(f"[AIOPS] 应用自定义查询条件: {len(custom_filters)} 个子句")

    # 应用 LLM 提取的用户条件到主查询（如 status>=500、device_ip=xxx 等）
    for uc in (user_conditions or []):
        es_clause = _build_single_es_condition(uc, es_meta)
        if es_clause:
            all_filters.append(es_clause)
    if user_conditions:
        print(f"[AIOPS] 主查询应用LLM提取条件: {len(user_conditions)}个 -> filters={len(all_filters)}")

    # === 聚合模式（有字段配置时） ===
    if fields:
        aggs = _build_es_aggregations(fields, range_seconds, es_meta)
        # size: AGG_SAMPLE_SIZE —— 聚合 + 最新样本日志（同一次请求同时拿到）
        es_query = {
            "query": {"bool": {"filter": all_filters}},
            "size": AGG_SAMPLE_SIZE,
            "sort": [{ts_field: "desc"}],
            "track_total_hits": True,
            "aggs": aggs,
        }
        try:
            result = await es_client.search(index=skill.index_pattern, query=es_query)
            hits_obj = result.get("hits", {})
            total_info = hits_obj.get("total", {})
            total_count = total_info.get("value", 0) if isinstance(total_info, dict) else 0
            aggs_result = result.get("aggregations", {})

            # 聚合统计 → LLM 可读摘要
            stats_text = _format_stats_for_llm(aggs_result, fields)

            # === 补充最新样本日志（解决"配置变更"等需要具体内容的查询） ===
            # ES 在 size>0 时同时返回 hits.hits，无需额外请求
            sample_hits = hits_obj.get("hits", [])
            if sample_hits:
                sample_logs = _convert_logs_tz([h["_source"] for h in sample_hits])
                sample_text = _format_sample_logs_for_llm(sample_logs, fields)
                if sample_text:
                    stats_text += "\n" + sample_text

            # === 命令执行日志专项查询（含 command 字段的技能） ===
            # 借鉴 SQLBot 的"执行查询"阶段：将 LLM 提取的 user_conditions
            # 应用为 ES 过滤条件，实现精准查询。
            # 例如：用户问"设备ip是192.168.37.3执行过什么命令" →
            #   LLM 提取出 {field:device_ip, op:eq, value:192.168.37.3}
            #   → ES 查询直接过滤该设备，只返回 31 条而非 682 条
            field_name_set = {f.get("name", "") for f in fields}
            cmd_total = 0
            cmd_returned = 0
            command_text = ""  # 命令日志单独存储，不再与 stats_text 混合截断
            if "command" in field_name_set:
                cmd_must = [{"exists": {"field": "command"}}]
                if "module" in field_name_set:
                    cmd_must.append({"term": {"module.keyword": "SHELL"}})
                if "event_name" in field_name_set:
                    cmd_must.append({"term": {"event_name.keyword": "SHELL_CMD"}})

                # 应用 LLM 提取的用户条件 + 技能管理中配置的查询过滤条件
                cmd_filters = [range_filter]
                # 应用技能级自定义过滤条件（跳过 module/event_name，因为命令日志已硬编码为 SHELL）
                cmd_custom_filters = _build_query_filters(
                    getattr(skill, "query_filter", None), es_meta,
                    skip_fields={"module", "event_name"}
                )
                if cmd_custom_filters:
                    cmd_filters.extend(cmd_custom_filters)
                    print(f"[AIOPS] 命令日志应用自定义过滤(已跳过module/event_name): {len(cmd_custom_filters)}个子句")
                filter_desc_parts = []
                for uc in (user_conditions or []):
                    es_clause = _build_single_es_condition(uc, es_meta)
                    if es_clause:
                        cmd_filters.append(es_clause)
                        filter_desc_parts.append(
                            f"{uc['field']}{uc['operator']}{uc['value']}")
                if filter_desc_parts:
                    filter_label = "（已按 " + ", ".join(filter_desc_parts) + " 过滤）"
                    print(f"[AIOPS] 命令日志应用LLM提取条件: {filter_desc_parts}")
                else:
                    filter_label = ""

                print(f"[AIOPS] 命令日志查询 cmd_filters({len(cmd_filters)}): {json.dumps(cmd_filters, ensure_ascii=False, default=str)}")
                cmd_query = {
                    "query": {"bool": {"must": cmd_must, "filter": cmd_filters}},
                    "size": COMMAND_LOG_SIZE,
                    "sort": [{ts_field: "desc"}],
                    "track_total_hits": True,
                }
                try:
                    cmd_result = await es_client.search(
                        index=skill.index_pattern, query=cmd_query)
                    cmd_hits_obj = cmd_result.get("hits", {})
                    cmd_total_info = cmd_hits_obj.get("total", {})
                    cmd_total = (cmd_total_info.get("value", 0)
                                 if isinstance(cmd_total_info, dict) else 0)
                    cmd_hits = cmd_hits_obj.get("hits", [])
                    cmd_returned = len(cmd_hits)
                    if cmd_hits:
                        cmd_logs = _convert_logs_tz(
                            [h["_source"] for h in cmd_hits])
                        command_text = _format_command_logs_for_llm(
                            cmd_logs, cmd_total, filter_label)
                except Exception as e:
                    print(f"[AIOPS] 命令日志专项查询失败: {e}")

            print(f"[AIOPS] ES聚合查询: index={skill.index_pattern}, "
                  f"ts_field={ts_field}, "
                  f"range=UTC[{gte_str} -> {lte_str}], "
                  f"total_hits={total_count}, aggs_keys={len(aggs_result)}, "
                  f"sample_logs={len(sample_hits)}, "
                  f"command_logs={cmd_returned}/{cmd_total}, "
                  f"filters={len(all_filters)}")

            return {
                "mode": "aggregation",
                "total": total_count,
                "gte_cst": gte_cst,
                "lte_cst": lte_cst,
                "stats_text": stats_text,
                "command_text": command_text,  # 命令日志单独存储，给予独立的上下文空间
            }
        except Exception as e:
            print(f"[AIOPS] ES聚合查询失败({e})，回退到样本模式")

    # === 样本模式（回退：无字段配置或聚合失败时） ===
    es_query = {
        "query": {"bool": {"filter": all_filters}},
        "sort": [{ts_field: "desc"}],
        "size": FALLBACK_SAMPLE_SIZE,
        "track_total_hits": True,
    }
    try:
        result = await es_client.search(index=skill.index_pattern, query=es_query)
        hits_obj = result.get("hits", {})
        total_info = hits_obj.get("total", {})
        total_count = total_info.get("value", 0) if isinstance(total_info, dict) else 0
        hits = hits_obj.get("hits", [])
        logs = _convert_logs_tz([h["_source"] for h in hits])
        sample_text = json.dumps(logs, ensure_ascii=False, indent=2)[:STATS_MAX_CHARS]

        print(f"[AIOPS] ES样本查询(回退): index={skill.index_pattern}, "
              f"range=UTC[{gte_str} -> {lte_str}], "
              f"total_hits={total_count}, sample={len(logs)}")

        return {
            "mode": "sample",
            "total": total_count,
            "gte_cst": gte_cst,
            "lte_cst": lte_cst,
            "stats_text": sample_text,
            "command_text": "",
        }
    except Exception as e:
        print(f"[AIOPS] ES查询失败: {e}")
        return {
            "mode": "error",
            "total": 0,
            "gte_cst": gte_cst,
            "lte_cst": lte_cst,
            "stats_text": f"ES查询失败: {str(e)}",
            "command_text": "",
        }
