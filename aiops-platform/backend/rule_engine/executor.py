"""动作执行器 - 执行规则匹配后的动作（告警触发/AI分析）"""

from typing import List, Optional
from rule_engine.evaluator import MatchResult
from core.llm_client import llm_client
from gateway.prompt_mgr import prompt_mgr
from models.alert_channel import AlertChannel
from models.event import Event, EventFingerprint
from models.rule import RuleType
from models.cmdb import CMDBAsset
from core.db import async_session_factory
from core.redis_client import redis_client
from sqlalchemy import select
import json
import hashlib
import uuid
import re
from datetime import datetime, timedelta, timezone


class ActionExecutor:
    """动作执行器"""

    async def execute(self, results: List[MatchResult]) -> List[dict]:
        """
        执行匹配结果的动作

        Args:
            results: 匹配结果列表
        Returns:
            触发的动作列表
        """
        from scanner.storm import storm_controller  # 延迟导入，避免循环引用

        actions = []

        for result in results:
            if not result.matched:
                continue

            rule = result.rule
            action_config = rule.action_config

            # 0. 频率阈值检查（可选：窗口内累计达标才触发）
            if not await self._check_threshold(rule, result.log):
                continue

            # 1. 创建/更新事件记录（含去重）
            is_new_event = await self._create_or_update_event(rule, result.log)

            # 2. 调用AI分析
            if action_config.get("call_ai", False):
                analysis = await self._call_ai_analysis(result, is_new_event=is_new_event)
                result.analysis_result = analysis

            # 3. 触发告警
            if action_config.get("alert", False):
                alert_action = await storm_controller.evaluate_and_alert(
                    rule=rule,
                    log=result.log,
                    analysis=result.analysis_result,
                    alert_fields=action_config.get("alert_fields", []),
                    alert_type=action_config.get("alert_type", "immediate"),
                )
                actions.append(alert_action)

        return actions

    async def _check_threshold(self, rule, log: dict) -> bool:
        """检查频率阈值，返回 True 表示达到阈值可以触发

        如果规则的 match_condition 中包含 threshold 配置：
          {"threshold": {"count": 10, "window_minutes": 5}}
        则使用 Redis 计数器，在窗口内累计达标后才触发。
        无 threshold 配置则立即触发（保持现有行为）。
        """
        match_condition = rule.match_condition or {}
        threshold = match_condition.get("threshold")
        if not threshold:
            return True  # 无阈值配置，立即触发

        count_limit = int(threshold.get("count", 1))
        window_minutes = int(threshold.get("window_minutes", 5))

        # 生成计数 key（按规则+设备/域名聚合）
        device = log.get("device_ip", "") or log.get("domain", "") or log.get("hostname", "") or "global"
        counter_key = f"rule_threshold:{rule.id}:{device}"

        current = await redis_client.incr(counter_key, ttl=window_minutes * 60)

        if current >= count_limit:
            # 达到阈值：删除计数器（重置窗口），允许触发
            await redis_client.delete(counter_key)
            print(f"[执行器] 规则'{rule.rule_name}' 设备{device} 频率阈值达标({current}/{count_limit}次/{window_minutes}分钟)，触发告警")
            return True

        return False

    def _build_summary(self, rule, log: dict, occurrence_count: int = 1,
                        first_seen: datetime = None, last_seen: datetime = None) -> str:
        """根据规则类型生成富摘要

        每种规则类型都有对应的摘要格式，包含关键业务信息。
        多次触发时显示时间范围和累计次数。
        """
        rule_type = rule.rule_type
        if hasattr(rule_type, 'value'):
            rule_type = rule_type.value

        rule_name = rule.rule_name

        # 计算时间范围字符串（多次触发时复用）
        # 将 UTC 时间转为 UTC+8（中国标准时间）再格式化
        time_range_str = ""
        today_count_str = ""  # 同一天内使用"今天累计xx次"
        is_same_day = False
        _CST = timezone(timedelta(hours=8))
        if occurrence_count > 1 and first_seen and last_seen:
            # 转 UTC+8
            fs_cst = first_seen.replace(tzinfo=timezone.utc).astimezone(_CST) if first_seen.tzinfo is None else first_seen.astimezone(_CST)
            ls_cst = last_seen.replace(tzinfo=timezone.utc).astimezone(_CST) if last_seen.tzinfo is None else last_seen.astimezone(_CST)
            if fs_cst.date() == ls_cst.date():
                # 同一天：显示"今天累计xx次"
                is_same_day = True
                today_count_str = f"今天累计{occurrence_count}次"
                t_start = fs_cst.strftime("%H:%M:%S")
                t_end = ls_cst.strftime("%H:%M:%S")
                time_range_str = f"{t_start}—{t_end}"
            else:
                t_start = fs_cst.strftime("%m-%d %H:%M")
                t_end = ls_cst.strftime("%m-%d %H:%M")
                time_range_str = f"{t_start}—{t_end}"

        # === HTTP 状态码告警 ===
        if rule_type == RuleType.HTTP_STATUS_ALERT.value:
            status_val = log.get("status", "")
            domain = log.get("domain", "") or log.get("hostname", "")
            request_path = log.get("request", "") or log.get("uri", "")
            if len(str(request_path)) > 60:
                request_path = str(request_path)[:60] + "..."
            if time_range_str:
                count_str = today_count_str if is_same_day else f"累计{occurrence_count}次"
                return f"[{rule_name}] {time_range_str} 状态码≥500 {count_str}（{domain}）"
            return f"[{rule_name}] 状态码{status_val}（{domain} {request_path}）"

        # === 响应时间告警 ===
        if rule_type == RuleType.RESPONSE_TIME_ALERT.value:
            resp_time = log.get("responsetime", "") or log.get("response_time", "")
            domain = log.get("domain", "") or log.get("hostname", "")
            request_path = log.get("request", "") or log.get("uri", "")
            if len(str(request_path)) > 60:
                request_path = str(request_path)[:60] + "..."
            if time_range_str:
                count_str = today_count_str if is_same_day else f"累计{occurrence_count}次"
                return f"[{rule_name}] {time_range_str} 响应超时 {count_str}（{domain}）"
            return f"[{rule_name}] 响应时间{resp_time}s（{domain} {request_path}）"

        # === 日志级别告警（severity_filter） ===
        if rule_type == RuleType.SEVERITY_FILTER.value:
            severity = log.get("severity", "")
            device = log.get("device_ip", "") or log.get("hostname", "")
            module = log.get("module", "")
            message = log.get("message", "")[:80]
            if time_range_str:
                count_str = today_count_str if is_same_day else f"累计{occurrence_count}次"
                return f"[{rule_name}] {time_range_str} 设备{device} 级别≤{severity} {count_str}（{module}）"
            module_str = f"/{module}" if module else ""
            return f"[{rule_name}] 设备{device} 级别{severity}{module_str}: {message}"

        # === 危险命令告警（dangerous_command） ===
        if rule_type == RuleType.DANGEROUS_COMMAND.value:
            device = log.get("device_ip", "") or log.get("hostname", "")
            user = log.get("user", "")
            src_ip = log.get("src_ip", "")
            command = log.get("command", "")[:80]
            who = f"{user}@{src_ip}" if user and src_ip else (user or src_ip or "未知")
            if time_range_str:
                count_str = today_count_str if is_same_day else f"累计{occurrence_count}次"
                return f"[{rule_name}] {time_range_str} 设备{device} 危险操作 {count_str}（{who}）"
            return f"[{rule_name}] {who}→{device} 执行: {command}"

        # === 命令执行监控（command_monitor） ===
        if rule_type == RuleType.COMMAND_MONITOR.value:
            device = log.get("device_ip", "") or log.get("hostname", "")
            user = log.get("user", "")
            src_ip = log.get("src_ip", "")
            command = log.get("command", "") or log.get("event_name", "")
            if len(str(command)) > 80:
                command = str(command)[:80] + "..."
            who = f"{user}@{src_ip}" if user and src_ip else (user or src_ip or "")
            if time_range_str:
                count_str = today_count_str if is_same_day else f"累计{occurrence_count}次"
                return f"[{rule_name}] {time_range_str} 设备{device} 命令操作 {count_str}（{who}）"
            return f"[{rule_name}] {who}→{device} 执行: {command}"

        # === 关键词匹配（keyword_match） ===
        if rule_type == RuleType.KEYWORD_MATCH.value:
            device = log.get("device_ip", "") or log.get("hostname", "") or log.get("client", "")
            message = log.get("message", "") or log.get("command", "") or log.get("event_name", "")
            if len(str(message)) > 100:
                message = str(message)[:100] + "..."
            if time_range_str:
                count_str = today_count_str if is_same_day else f"累计{occurrence_count}次"
                return f"[{rule_name}] {time_range_str} 设备{device} 关键词命中 {count_str}"
            return f"[{rule_name}] 设备{device}: {message}"

        # === 指标阈值告警（metric_threshold） ===
        if rule_type == RuleType.METRIC_THRESHOLD.value:
            metric_name = log.get("metric_name", "")
            metric_value = log.get("metric_value", "")
            instance = log.get("instance", "")
            job = log.get("job", "")
            # 提取接口/设备/路径等关键维度，优先展示接口名
            interface_keys = ["ifname", "name", "interface", "ifDescr", "ifAlias"]
            interface_name = ""
            for k in interface_keys:
                if log.get(k):
                    interface_name = str(log.get(k))
                    break
            interface_str = f" 接口[{interface_name}]" if interface_name else ""
            if time_range_str:
                count_str = today_count_str if is_same_day else f"累计{occurrence_count}次"
                return f"[{rule_name}] {time_range_str} 实例{instance}{interface_str} {metric_name}异常 {count_str}"
            return f"[{rule_name}] 实例{instance}{interface_str} {metric_name}={metric_value}({job})"

        # === 其他/通用规则 ===
        message = log.get("message", "") or log.get("command", "") or log.get("event_name", "")
        device = log.get("device_ip", "") or log.get("hostname", "") or log.get("client", "")
        if time_range_str:
            count_str = today_count_str if is_same_day else f"累计{occurrence_count}次"
            return f"[{rule_name}] {time_range_str} {device} {count_str} {message[:100]}"
        if device:
            return f"[{rule_name}] {device}: {message[:150]}"
        return f"[{rule_name}] {message[:200]}"

    async def _create_or_update_event(self, rule, log: dict):
        """创建或更新事件记录（基于指纹去重）

        Returns:
            bool: True 表示新建事件（首次出现），False 表示命中已有事件（重复）
        """
        risk_level = rule.risk_level
        if hasattr(risk_level, 'value'):
            risk_level = risk_level.value
        risk_level = str(risk_level).lower()

        rule_type = rule.rule_type
        if hasattr(rule_type, 'value'):
            rule_type = rule_type.value

        # 提取设备标识：优先 ES 字段，回退到 Prometheus 的 instance 字段
        source_device = (
            log.get("device_ip", "")
            or log.get("hostname", "")
            or log.get("client", "")
            or log.get("device", "")
            or ""
        )
        source_ip = log.get("src_ip", "") or log.get("client", "") or ""

        # Prometheus 指标记录的 instance 字段（格式 "IP:port"），提取 IP 部分
        if not source_ip and log.get("instance"):
            raw_instance = str(log["instance"])
            source_ip = raw_instance.split(":")[0] if ":" in raw_instance else raw_instance

        # 如果设备名还是空，用 instance 的 IP 兜底
        if not source_device and source_ip:
            source_device = source_ip

        # 从 CMDB 查找设备名称（按 IP 匹配），将 IP 替换为可读设备名
        try:
            from models.cmdb import CMDBAsset
            # 确定用于 CMDB 查询的 IP
            _lookup_ip = source_ip or source_device
            if _lookup_ip:
                async with async_session_factory() as _s:
                    _r = await _s.execute(
                        select(CMDBAsset.name).where(CMDBAsset.ip_address == _lookup_ip).limit(1)
                    )
                    _row = _r.scalar_one_or_none()
                    if _row:
                        source_device = _row  # 用 CMDB 设备名替换 IP
        except Exception as _e:
            pass  # CMDB 查询失败不影响主流程

        # HTTP 类规则按 rule_id + domain 去重（同一域名的状态码告警归为一条）
        if rule_type in (RuleType.HTTP_STATUS_ALERT.value, RuleType.RESPONSE_TIME_ALERT.value):
            domain = log.get("domain", "") or log.get("hostname", "")
            fp_raw = f"{rule.id}:{rule_type}:{domain}"
        else:
            message = log.get("message", "") or log.get("command", "") or log.get("event_name", "")
            fp_raw = f"{rule.id}:{rule_type}:{source_device}:{message[:100]}"
        fingerprint = hashlib.md5(fp_raw.encode()).hexdigest()

        try:
            async with async_session_factory() as session:
                # 检查是否已存在同指纹事件
                result = await session.execute(
                    select(EventFingerprint).where(EventFingerprint.fingerprint == fingerprint)
                )
                existing_fp = result.scalar_one_or_none()

                if existing_fp:
                    # 已存在：更新计数和时间
                    existing_fp.count += 1
                    existing_fp.last_seen = datetime.now()

                    evt_result = await session.execute(
                        select(Event).where(Event.event_id == existing_fp.event_id)
                    )
                    evt = evt_result.scalar_one_or_none()
                    if evt:
                        evt.occurrence_count = (evt.occurrence_count or 1) + 1
                        evt.last_seen = datetime.now()
                        # 更新摘要：包含时间范围和累计次数
                        evt.summary = self._build_summary(
                            rule, log,
                            occurrence_count=evt.occurrence_count,
                            first_seen=evt.first_seen,
                            last_seen=evt.last_seen,
                        )
                    await session.commit()
                    return False
                else:
                    # 新事件
                    event_id = str(uuid.uuid4())
                    now = datetime.now()
                    summary = self._build_summary(rule, log, occurrence_count=1,
                                                  first_seen=now, last_seen=now)
                    raw_log = json.dumps(log, ensure_ascii=False, default=str)[:2000]

                    event = Event(
                        event_id=event_id,
                        skill_id=rule.skill_id,
                        event_type=str(rule_type),
                        risk_level=risk_level,
                        summary=summary,
                        source_device=source_device,
                        source_ip=source_ip,
                        raw_log=raw_log,
                        first_seen=now,
                        last_seen=now,
                    )
                    session.add(event)

                    fp = EventFingerprint(
                        fingerprint=fingerprint,
                        event_id=event_id,
                        first_seen=now,
                        last_seen=now,
                        count=1,
                    )
                    session.add(fp)
                    await session.commit()
                    return True
        except Exception as e:
            print(f"[执行器] 创建事件失败: {str(e)}")
            return True

    async def _call_ai_analysis(self, result: MatchResult, is_new_event: bool = True) -> str:
        """调用AI分析

        Args:
            result: 匹配结果
            is_new_event: 是否为首次生成的事件（上下文联合分析据此控制调用成本）
        """
        rule = result.rule
        log = result.log
        action_config = rule.action_config or {}
        analysis_type = action_config.get("ai_analysis", "")

        # 如果开启了 AI 分析但未指定分析类型，根据规则类型智能推断
        if not analysis_type and action_config.get("call_ai", False):
            rule_type = rule.rule_type
            if hasattr(rule_type, 'value'):
                rule_type = rule_type.value
            type_inference = {
                RuleType.DANGEROUS_COMMAND.value: "command_analysis",
                RuleType.COMMAND_MONITOR.value: "command_analysis",
            }
            analysis_type = type_inference.get(rule_type, "")
            print(f"[AI分析] 规则 '{rule.rule_name}' 未指定分析类型，根据规则类型推断为: {analysis_type or '无'}")

        # 根据分析类型选择Prompt
        template_map = {
            "emotion_scan": "emotion_scan.tpl",
            "command_analysis": "command_analysis.tpl",
            "root_cause": "h3c_net_analysis.tpl",
            "business_report": "nginx_business_report.tpl",
            "context_correlation": "context_analysis.tpl",
        }

        template_name = template_map.get(analysis_type, "")
        if not template_name:
            print(f"[AI分析] 规则 '{rule.rule_name}' 未找到对应分析类型 '{analysis_type}' 的Prompt模板")
            return ""

        print(f"[AI分析] 规则 '{rule.rule_name}' 使用模板: {template_name}")

        # 从模型调度器获取可用模型配置（支持后台配置中心动态配置）
        from gateway.model_scheduler import model_scheduler
        model_cfg = await model_scheduler.get_model()
        if not model_cfg:
            print(f"[AI分析] 规则 '{rule.rule_name}' 未找到可用的大模型配置")
            return "[AI分析失败] 未找到可用的大模型配置，请在配置中心添加并启用LLM"

        print(f"[AI分析] 规则 '{rule.rule_name}' 使用模型: {model_cfg.get('name')}({model_cfg.get('model_name')})")

        # 上下文联合分析：拉取同设备、时间窗内的多条日志一并交给大模型
        if analysis_type == "context_correlation":
            ai_ctx = action_config.get("ai_context", {}) or {}
            if ai_ctx.get("enabled", True):
                # 仅首次事件执行，控制 AI 调用成本（可通过 on_new_event_only=false 关闭该限制）
                if ai_ctx.get("on_new_event_only", True) and not is_new_event:
                    print(f"[AI分析] 规则 '{rule.rule_name}' 上下文分析跳过（非首次事件，节省Token）")
                    return ""
                window_minutes = int(ai_ctx.get("window_minutes", 10))
                max_logs = int(ai_ctx.get("max_logs", 50))
                same_device_only = bool(ai_ctx.get("same_device_only", True))
                context_logs = await self._fetch_context_logs(
                    rule, log, window_minutes, max_logs, same_device_only
                )
                if not context_logs:
                    context_logs = [log]
                print(f"[AI分析] 规则 '{rule.rule_name}' 上下文联合分析：拉取 {len(context_logs)} 条日志（窗口 {window_minutes}m）")
                logs_payload = json.dumps(context_logs, ensure_ascii=False, indent=2, default=str)
                time_range_str = f"{window_minutes}m"
            else:
                logs_payload = json.dumps(log, ensure_ascii=False, indent=2, default=str)
                time_range_str = "5m"
        else:
            logs_payload = json.dumps(log, ensure_ascii=False, indent=2, default=str)
            time_range_str = "5m"

        prompt = await prompt_mgr.get_prompt(
            template_name,
            severity=log.get("severity", ""),
            message=log.get("message", ""),
            device_ip=log.get("device_ip", ""),
            hostname=log.get("hostname", ""),
            module=log.get("module", ""),
            user=log.get("user", ""),
            src_ip=log.get("src_ip", ""),
            command=log.get("command", ""),
            event_name=log.get("event_name", ""),
            logs=logs_payload,
            time_range=time_range_str,
        )

        try:
            response = await llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model_cfg.get("model_name"),
                temperature=0.3,
                api_base=model_cfg.get("api_base"),
                api_key=model_cfg.get("api_key"),
            )
            print(f"[AI分析] 规则 '{rule.rule_name}' 分析结果长度: {len(response) if response else 0}")
            return response
        except Exception as e:
            print(f"[AI分析] 规则 '{rule.rule_name}' 调用失败: {str(e)}")
            return f"[AI分析失败] {str(e)}"

    async def _fetch_context_logs(self, rule, log: dict, window_minutes: int,
                                   max_logs: int, same_device_only: bool) -> list:
        """拉取同设备、时间窗内的上下文日志，用于 AI 联合分析

        按规则关联技能的 index_pattern 检索 ES：
        - 时间范围：最近 window_minutes 分钟
        - 设备过滤：same_device_only=True 时按触发日志的 device_ip / hostname 过滤
        - 数量：最多 max_logs 条，按时间倒序
        """
        from core.es_client import es_client
        from models.skill import Skill

        index_pattern = None
        try:
            async with async_session_factory() as session:
                r = await session.execute(select(Skill).where(Skill.id == rule.skill_id))
                skill = r.scalar_one_or_none()
                if skill:
                    index_pattern = skill.index_pattern
        except Exception as e:
            print(f"[上下文分析] 加载技能索引失败: {e}")

        if not index_pattern:
            print(f"[上下文分析] 规则 '{rule.rule_name}' 关联技能无 index_pattern，跳过上下文检索")
            return []

        filters = [
            {"range": {"@timestamp": {"gte": f"now-{window_minutes}m", "lte": "now"}}}
        ]
        if same_device_only:
            device_ip = log.get("device_ip") or ""
            hostname = log.get("hostname") or ""
            if device_ip:
                filters.append({"match_phrase": {"device_ip": device_ip}})
            elif hostname:
                filters.append({"match_phrase": {"hostname": hostname}})

        query = {
            "query": {"bool": {"filter": filters}},
            "sort": [{"@timestamp": "desc"}],
            "size": max_logs,
        }

        try:
            res = await es_client.search(index_pattern, query, size=max_logs)
            hits = res.get("hits", {}).get("hits", [])
            return [h.get("_source", {}) for h in hits]
        except Exception as e:
            print(f"[上下文分析] 规则 '{rule.rule_name}' ES 检索失败: {e}")
            return []

    async def send_alert(self, rule, log: dict, analysis: Optional[str], alert_fields: list, alert_type: str) -> dict:
        """发送告警通知"""
        # 构建告警消息
        alert_msg = await self._build_alert_message(rule, log, analysis, alert_fields)

        # 根据规则 action_config 中的 alert_channels 决定发送渠道
        action_config = rule.action_config or {}
        alert_channel_ids = action_config.get("alert_channels")

        from services.notifier import notifier
        print(f"[告警发送] 规则 '{rule.rule_name}' 准备发送，指定渠道: {alert_channel_ids or '全部启用渠道'}")
        if isinstance(alert_channel_ids, list) and len(alert_channel_ids) > 0:
            sent_results = await notifier.notify_by_channels(alert_msg, alert_channel_ids)
        else:
            sent_results = await notifier.notify_all(alert_msg)

        print(f"[告警发送] 规则 '{rule.rule_name}' 发送结果: {sent_results}")

        return {
            "alert_type": alert_type,
            "risk_level": rule.risk_level.value if hasattr(rule.risk_level, 'value') else rule.risk_level,
            "rule_name": rule.rule_name,
            "message": alert_msg,
            "channels": sent_results,
        }

    # ============ 告警消息模板系统 ============

    # 风险等级中文映射
    RISK_LEVEL_MAP = {
        "low": "低", "medium": "中", "high": "高", "critical": "紧急",
    }

    # topic -> 区域映射（业务监控日志常用）
    # 精确匹配优先；如未命中，会再尝试按子串包含匹配
    TOPIC_REGION_MAP = {
        "nginx-access-log-8ov": "政务外网",
        "nginx-access-log-int": "互联网",
    }

    # 各规则类型的默认告警模板（支持 {field_name} 变量替换）
    DEFAULT_ALERT_TEMPLATES = {
        RuleType.RESPONSE_TIME_ALERT.value: (
            "**[{rule_name}] 告警**\n\n"
            "> 告警级别：{risk_level}\n\n"
            "- 设备名称：{hostname}\n"
            "- 涉及域名：{domain}\n"
            "- 涉及接口：{request}\n"
            "- 响应时间：{responsetime}s\n"
        ),
        RuleType.HTTP_STATUS_ALERT.value: (
            "**[{rule_name}] 告警**\n\n"
            "> 告警级别：{risk_level}\n\n"
            "- 涉及域名：{domain}\n"
            "- 涉及接口：{request}\n"
            "- 状态码：{status}\n"
            "- 客户端IP：{client}\n"
        ),
        RuleType.SEVERITY_FILTER.value: (
            "**[{rule_name}] 告警**\n\n"
            "> 告警级别：{risk_level}\n\n"
            "- 设备IP：{device_ip}\n"
            "- 日志级别：{severity}\n"
            "- 模块：{module}\n"
            "- 详情：{message}\n"
        ),
        RuleType.DANGEROUS_COMMAND.value: (
            "**[{rule_name}] 告警**\n\n"
            "> 告警级别：{risk_level}\n\n"
            "- 设备IP：{device_ip}\n"
            "- 操作用户：{user}\n"
            "- 来源IP：{src_ip}\n"
            "- 执行命令：{command}\n"
        ),
        RuleType.COMMAND_MONITOR.value: (
            "**[{rule_name}] 告警**\n\n"
            "> 告警级别：{risk_level}\n\n"
            "- 设备IP：{device_ip}\n"
            "- 操作用户：{user}\n"
            "- 来源IP：{src_ip}\n"
            "- 执行命令：{command}\n"
        ),
        RuleType.KEYWORD_MATCH.value: (
            "**[{rule_name}] 告警**\n\n"
            "> 告警级别：{risk_level}\n\n"
            "- 设备IP：{device_ip}\n"
            "- 主机名：{hostname}\n"
            "- 匹配内容：{message}\n"
        ),
        RuleType.METRIC_THRESHOLD.value: (
            "**[{rule_name}] 指标告警**\n\n"
            "> 告警级别：{risk_level}\n\n"
            "- 实例：{instance}\n"
            "- 指标名：{metric_name}\n"
            "- 当前值：{metric_value}\n"
            "- 触发阈值：{operator} {threshold}\n"
            "- 任务：{job}\n"
        ),
    }

    # 通用兜底模板
    FALLBACK_TEMPLATE = (
        "**[{rule_name}] 告警**\n\n"
        "> 告警级别：{risk_level}\n\n"
        "- 设备：{device_ip}\n"
        "- 详情：{message}\n"
    )

    def _format_cst_timestamp(self, ts_value) -> str:
        """将日志时间字段转换为东八区（CST）可读格式"""
        if not ts_value:
            return ""
        ts_str = str(ts_value).strip()
        # 常见格式：2026-07-14T03:34:35.865752099Z 或 2026-07-14 03:34:35
        try:
            # 去掉末尾的 Z
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1]
            # 处理带微秒的 ISO 格式
            if "." in ts_str:
                # 只保留前6位微秒，避免 Python 不支持超过6位
                base, micro = ts_str.split(".", 1)
                micro = micro[:6].ljust(6, "0")
                ts_str = f"{base}.{micro}"
            dt = datetime.fromisoformat(ts_str)
            # 如果原始时间没有时区，假设为 UTC；否则按原时区转换
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            cst = dt.astimezone(timezone(timedelta(hours=8)))
            return cst.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return ts_str

    async def _build_alert_message(self, rule, log: dict, analysis: Optional[str], alert_fields: list) -> str:
        """构建告警消息文本

        模板优先级：
        1. rule.action_config['alert_template'] - 用户自定义模板
        2. DEFAULT_ALERT_TEMPLATES[rule_type] - 规则类型默认模板
        3. FALLBACK_TEMPLATE - 通用兜底模板

        模板变量：
        - {rule_name}: 规则名称
        - {risk_level}: 风险等级（中文）
        - {threshold}: 指标阈值（仅 metric_threshold 规则）
        - {device_name}: 设备名称（从 CMDB 资产管理根据 IP 查询）
        - {region}: 区域（优先 CMDB；如 CMDB 无区域，业务日志按 topic 映射）
        - {datacenter}: 机房（从 CMDB 查询）
        - {owner}: 负责人（从 CMDB 查询）
        - {asset_type}: 资产类型（从 CMDB 查询）
        - {timestamp}: 触发时间（东八区，格式 YYYY-MM-DD HH:mm:ss）
        - {ai_analysis}: AI 风险分析摘要（需开启 call_ai）
        - {字段名}: 日志中的任何字段，如 {domain}, {hostname}, {log_type}, {topic}, {@timestamp} 等
        """
        rule_type = rule.rule_type
        if hasattr(rule_type, 'value'):
            rule_type = rule_type.value

        # 获取风险等级中文
        risk_raw = rule.risk_level.value if hasattr(rule.risk_level, 'value') else rule.risk_level
        risk_level_cn = self.RISK_LEVEL_MAP.get(str(risk_raw).lower(), str(risk_raw))

        # 选择模板
        action_config = rule.action_config or {}
        custom_template = action_config.get("alert_template", "").strip()

        if custom_template:
            template = custom_template
            print(f"[告警模板] 规则 '{rule.rule_name}' 使用自定义模板")
        else:
            template = self.DEFAULT_ALERT_TEMPLATES.get(rule_type, self.FALLBACK_TEMPLATE)
            print(f"[告警模板] 规则 '{rule.rule_name}' 使用默认模板")

        # 修复常见 Markdown 加粗语法错误：** text** / **text ** -> **text**
        template = re.sub(r'\*\*\s+(.+?)\s*\*\*', r'**\1**', template)

        # 构建变量字典（log字段 + 特殊字段）
        variables = {k: (str(v) if v is not None else "") for k, v in log.items()}
        variables["rule_name"] = rule.rule_name
        variables["risk_level"] = risk_level_cn

        # 时间字段格式化（东八区）
        ts_raw = log.get("@timestamp") or log.get("timestamp") or log.get("time")
        cst_time = self._format_cst_timestamp(ts_raw)
        if cst_time:
            variables["timestamp"] = cst_time
            variables["@timestamp"] = cst_time

        # AI 分析摘要（告警中保持精简，避免过长）
        variables["ai_analysis"] = analysis[:40] if analysis else "未启用AI分析"
        variables["risk_analysis"] = variables["ai_analysis"]

        # metric_threshold 额外注入阈值信息（支持单条件与多条件配置）
        match_condition = rule.match_condition or {}
        self._inject_metric_threshold(match_condition, log, variables)

        # 注入 CMDB 资产信息（设备名称、区域、机房、负责人等）
        await self._enrich_variables_from_cmdb(log, variables)

        # 业务监控：按 topic 字段映射区域（仅在 CMDB 未提供区域时生效）
        self._apply_topic_region_mapping(log, variables)

        # 安全渲染模板（缺失字段显示为空而非报错）
        try:
            from string import Formatter
            formatter = Formatter()
            rendered = formatter.vformat(template, (), _SafeDict(variables))
        except Exception as e:
            print(f"[告警模板] 规则 '{rule.rule_name}' 渲染失败: {e}")
            rendered = f"**[{rule.rule_name}] 告警**\n\n告警级别：{risk_level_cn}\n"

        # 追加 AI 分析结果（若模板中未使用 ai_analysis 变量，仍保留默认追加）
        if analysis and "{ai_analysis}" not in template and "{risk_analysis}" not in template:
            rendered += f"\n**AI分析**：\n{analysis[:100]}\n"

        rendered += "\n---\nAIOPS 智能运维平台"
        return rendered

    def _inject_metric_threshold(self, match_condition: dict, log: dict, variables: dict):
        """为 metric_threshold 规则注入 {threshold} / {operator} 变量

        - 单条件：直接取顶层 value / operator
        - 多条件：按实际触发的 metric_name 匹配对应 condition，取其 value / operator
          （注意：match_condition['threshold'] 是频率去重阈值 {count, window_minutes}，
          不能用作指标阈值）
        """
        conditions = match_condition.get("conditions")
        if isinstance(conditions, list) and conditions:
            data_metric = log.get("metric_name", "")
            matched = next((c for c in conditions if c.get("metric") == data_metric), None)
            # 未能按指标名匹配时退回第一个条件，避免变量为空
            matched = matched or conditions[0]
            source = matched
        else:
            source = match_condition

        if source.get("value") is not None:
            variables.setdefault("threshold", str(source["value"]))
        if source.get("operator"):
            variables.setdefault("operator", str(source["operator"]))

    async def _enrich_variables_from_cmdb(self, log: dict, variables: dict):
        """根据日志中的 IP 查询 CMDB 资产管理，注入设备名称/区域/机房/负责人等变量

        优先从 device_ip、ip、hostname、client、instance、host 等字段中提取 IPv4，
        然后在 cmdb_assets 表中按 IP 查找，把第一个匹配资产的字段注入 variables。
        若 CMDB 中不存在，则保持原值不变。
        """
        ip_candidates = []
        for field in ("device_ip", "ip", "hostname", "client", "instance", "host"):
            val = log.get(field)
            if not val:
                continue
            if isinstance(val, str):
                ip_candidates.extend([v.strip() for v in val.split(",") if v.strip()])
            elif isinstance(val, list):
                ip_candidates.extend([str(v).strip() for v in val if v])

        if not ip_candidates:
            return

        # 提取有效 IPv4
        ipv4_re = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        ips = set()
        for candidate in ip_candidates:
            for ip in ipv4_re.findall(str(candidate)):
                parts = ip.split(".")
                try:
                    if all(0 <= int(p) <= 255 for p in parts):
                        ips.add(ip)
                except ValueError:
                    continue
            if len(ips) >= 5:
                break

        if not ips:
            return

        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(CMDBAsset).where(CMDBAsset.ip_address.in_(list(ips)))
                )
                assets = result.scalars().all()
                if assets:
                    asset = assets[0]
                    variables.setdefault("device_name", asset.name or "")
                    variables.setdefault("region", asset.region or "")
                    variables.setdefault("datacenter", asset.datacenter or "")
                    variables.setdefault("owner", asset.owner or "")
                    variables.setdefault("asset_type", asset.asset_type or "")
                    variables.setdefault("organization", asset.organization or "")
        except Exception as e:
            print(f"[告警模板CMDB查询失败] {e}")

    def _apply_topic_region_mapping(self, log: dict, variables: dict):
        """业务监控：按日志 topic 字段映射区域（仅当 CMDB 未提供区域时生效）

        当前内置映射：
        - nginx-access-log-8ov -> 政务外网
        - nginx-access-log-int -> 互联网
        """
        # 若 CMDB 已提供区域，不再覆盖
        if variables.get("region"):
            return

        topic = log.get("topic") or variables.get("topic")
        if not topic:
            return

        topic = str(topic).strip()

        # 精确匹配
        if topic in self.TOPIC_REGION_MAP:
            variables["region"] = self.TOPIC_REGION_MAP[topic]
            return

        # 子串包含匹配（兼容 topic 后缀变化，如 nginx-access-log-8ov-2024）
        for prefix, region in self.TOPIC_REGION_MAP.items():
            if prefix in topic:
                variables["region"] = region
                return


class _SafeDict(dict):
    """安全字典：模板变量缺失时返回空字符串而非抛异常"""
    def __missing__(self, key):
        return ""


# 全局单例
action_executor = ActionExecutor()