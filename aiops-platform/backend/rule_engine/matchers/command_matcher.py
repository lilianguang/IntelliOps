"""命令行为匹配器 - command_monitor / keyword_match / ignore_rule 规则"""


class CommandMatcher:
    """命令行为匹配器

    支持单条件（向后兼容）和多条件组合：
    - 单条件: {"field": "command", "operator": "contains", "value": "shutdown"}
    - 多条件: {"logic": "OR", "conditions": [{...}, {...}]}
    """

    async def match(self, log: dict, match_condition: dict) -> bool:
        """检查日志是否匹配命令监控条件"""
        conditions = match_condition.get("conditions")
        if isinstance(conditions, list) and len(conditions) > 0:
            logic = match_condition.get("logic", "OR").upper()
            results = [self._match_single(log, c) for c in conditions]
            if logic == "AND":
                return all(results)
            return any(results)

        # 向后兼容：扁平单条件
        return self._match_single(log, match_condition)

    def _match_single(self, log: dict, condition: dict) -> bool:
        """单个条件匹配"""
        field = condition.get("field", "event_name")
        operator = condition.get("operator", "contains")
        value = condition.get("value")

        log_value = log.get(field)
        if log_value is None:
            return False

        log_str = str(log_value)
        val_str = str(value)

        if operator == "contains":
            return val_str.lower() in log_str.lower()
        elif operator == "equals":
            return log_str == val_str
        elif operator == "startswith":
            return log_str.lower().startswith(val_str.lower())
        elif operator == "regex":
            import re
            return bool(re.search(val_str, log_str))
        return False


# 全局单例
command_matcher = CommandMatcher()