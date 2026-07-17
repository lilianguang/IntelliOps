"""HTTP状态码/响应时间匹配器 - http_status_alert / response_time_alert 规则"""


class HttpMatcher:
    """HTTP匹配器

    支持单条件（向后兼容）和多条件组合：
    - 单条件: {"field": "status", "operator": ">=", "value": 500}
    - 多条件: {"logic": "OR", "conditions": [{...}, {...}]}
    """

    async def match_status(self, log: dict, match_condition: dict) -> bool:
        """匹配HTTP状态码"""
        conditions = match_condition.get("conditions")
        if isinstance(conditions, list) and len(conditions) > 0:
            logic = match_condition.get("logic", "OR").upper()
            results = [self._match_status_single(log, c) for c in conditions]
            if logic == "AND":
                return all(results)
            return any(results)
        return self._match_status_single(log, match_condition)

    def _match_status_single(self, log: dict, condition: dict) -> bool:
        """单个状态码条件匹配"""
        field = condition.get("field", "status")
        operator = condition.get("operator", ">=")
        value = condition.get("value")

        log_value = log.get(field)
        if log_value is None:
            return False

        try:
            log_val = int(log_value)
            threshold = int(value)
        except (ValueError, TypeError):
            return str(log_value) == str(value)

        if operator == ">=":
            return log_val >= threshold
        elif operator == ">":
            return log_val > threshold
        elif operator == "==":
            return log_val == threshold
        elif operator == "<":
            return log_val < threshold
        elif operator == "<=":
            return log_val <= threshold
        return False

    async def match_response_time(self, log: dict, match_condition: dict) -> bool:
        """匹配响应时间"""
        conditions = match_condition.get("conditions")
        if isinstance(conditions, list) and len(conditions) > 0:
            logic = match_condition.get("logic", "OR").upper()
            results = [self._match_response_time_single(log, c) for c in conditions]
            if logic == "AND":
                return all(results)
            return any(results)
        return self._match_response_time_single(log, match_condition)

    def _match_response_time_single(self, log: dict, condition: dict) -> bool:
        """单个响应时间条件匹配"""
        field = condition.get("field", "responsetime")
        operator = condition.get("operator", ">")
        value = condition.get("value")

        log_value = log.get(field)
        if log_value is None:
            return False

        try:
            log_val = float(log_value)
            threshold = float(value)
        except (ValueError, TypeError):
            return False

        if operator == ">":
            return log_val > threshold
        elif operator == ">=":
            return log_val >= threshold
        elif operator == "<":
            return log_val < threshold
        elif operator == "<=":
            return log_val <= threshold
        return False


# 全局单例
http_matcher = HttpMatcher()