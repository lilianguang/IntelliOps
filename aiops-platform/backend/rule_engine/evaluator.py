"""规则评估器 - 多级匹配调度核心"""

from typing import List, Optional, Dict
from models.rule import Rule, RuleType
from rule_engine.loader import rule_loader
from rule_engine.filter import exclude_filter
from rule_engine.matchers.severity_matcher import severity_matcher
from rule_engine.matchers.command_matcher import command_matcher
from rule_engine.matchers.http_matcher import http_matcher
from rule_engine.matchers.es_query_matcher import es_query_matcher
from rule_engine.matchers.metric_matcher import metric_matcher


class MatchResult:
    """匹配结果"""
    def __init__(self, rule: Rule, matched: bool, log: dict):
        self.rule = rule
        self.matched = matched
        self.log = log
        self.analysis_result: Optional[str] = None

    @property
    def should_alert(self) -> bool:
        return self.matched and self.rule.action_config.get("alert", False)

    @property
    def should_call_ai(self) -> bool:
        return self.matched and self.rule.action_config.get("call_ai", False)

    @property
    def alert_type(self) -> str:
        return self.rule.action_config.get("alert_type", "immediate")

    @property
    def alert_fields(self) -> list:
        return self.rule.action_config.get("alert_fields", [])


class RuleEvaluator:
    """规则评估器"""

    async def evaluate(self, log: dict, rules: List[Rule]) -> List[MatchResult]:
        """
        对一条日志执行所有规则匹配

        匹配顺序（按优先级）：
        1. ignore_rule → 匹配则跳过后续所有
        2. dangerous_command
        3. severity_filter
        4. command_monitor
        5. http_status_alert / response_time_alert
        6. keyword_match / ai_analysis_trigger
        """
        results = []

        for rule in rules:
            # 检查忽略规则
            if rule.rule_type == RuleType.IGNORE_RULE:
                should_skip = await self._match_ignore(log, rule)
                if should_skip:
                    # 匹配忽略规则，整条日志跳过
                    return []

            # 执行匹配
            matched = await self._match_rule(log, rule)
            result = MatchResult(rule, matched, log)
            results.append(result)

        return results

    async def evaluate_batch(self, logs: List[dict], rules: List[Rule]) -> Dict[str, List[MatchResult]]:
        """批量评估多条日志"""
        results = {}
        for log in logs:
            log_id = log.get("_id", str(id(log)))
            results[log_id] = await self.evaluate(log, rules)
        return results

    async def _match_ignore(self, log: dict, rule: Rule) -> bool:
        """检查是否匹配忽略规则"""
        if rule.exclude_condition:
            return await exclude_filter.should_skip(log, rule.exclude_condition)
        return await self._match_condition(log, rule.match_condition, rule.rule_type)

    async def _match_rule(self, log: dict, rule: Rule) -> bool:
        """执行单个规则的匹配"""
        # 先检查排除条件
        if rule.exclude_condition:
            if await exclude_filter.should_skip(log, rule.exclude_condition):
                return False

        return await self._match_condition(log, rule.match_condition, rule.rule_type)

    async def _match_condition(self, log: dict, condition: dict, rule_type: RuleType) -> bool:
        """根据规则类型选择匹配器"""
        if rule_type in (RuleType.DANGEROUS_COMMAND,):
            return await es_query_matcher.match(log, condition.get("es_query", {}))

        if rule_type == RuleType.SEVERITY_FILTER:
            return await severity_matcher.match(log, condition)

        if rule_type in (RuleType.COMMAND_MONITOR, RuleType.KEYWORD_MATCH):
            return await command_matcher.match(log, condition)

        if rule_type == RuleType.HTTP_STATUS_ALERT:
            return await http_matcher.match_status(log, condition)

        if rule_type == RuleType.RESPONSE_TIME_ALERT:
            return await http_matcher.match_response_time(log, condition)

        if rule_type == RuleType.AI_ANALYSIS_TRIGGER:
            # AI分析触发规则由定时任务管理，不做实时匹配
            return False

        if rule_type == RuleType.METRIC_THRESHOLD:
            return await metric_matcher.match(log, condition)

        if rule_type == RuleType.IGNORE_RULE:
            return await command_matcher.match(log, condition)

        return False


# 全局单例
rule_evaluator = RuleEvaluator()