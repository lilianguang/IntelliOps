"""日志级别匹配器 - severity_filter 规则"""


class SeverityMatcher:
    """日志级别匹配器

    支持单条件（向后兼容）和多条件组合：
    - 单条件: {"field": "severity", "operator": "<=", "value": 3}
    - 多条件: {"logic": "OR", "conditions": [{...}, {...}]}
    """

    async def match(self, log: dict, match_condition: dict) -> bool:
        """检查日志是否匹配 severity 条件"""
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
        field = condition.get("field", "severity")
        operator = condition.get("operator", "<=")
        value = condition.get("value")

        log_value = log.get(field)
        if log_value is None:
            return False

        try:
            log_val = int(log_value)
            threshold = int(value)
        except (ValueError, TypeError):
            return str(log_value) == str(value)

        if operator == "<=":
            return log_val <= threshold
        elif operator == "<":
            return log_val < threshold
        elif operator == ">=":
            return log_val >= threshold
        elif operator == ">":
            return log_val > threshold
        elif operator == "==":
            return log_val == threshold
        return False


# 全局单例
severity_matcher = SeverityMatcher()