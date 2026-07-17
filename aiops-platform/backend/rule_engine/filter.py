"""排除过滤器 - 忽略规则检查"""

from typing import Optional


class ExcludeFilter:
    """排除过滤器：检查日志是否匹配忽略规则"""

    async def should_skip(self, log: dict, exclude_condition: Optional[dict]) -> bool:
        """
        判断是否应该跳过此日志

        Args:
            log: 日志条目
            exclude_condition: 排除条件（JSON）
        Returns:
            True=应跳过, False=不跳过
        """
        if not exclude_condition:
            return False

        # 处理不同的排除条件格式
        if "conditions" in exclude_condition:
            # 多条件格式: {conditions: [{field, operator, value}, ...]}
            # 任一条件匹配即排除（OR 逻辑）
            for cond in exclude_condition["conditions"]:
                if self._check_field_exclude(log, cond):
                    return True
            return False

        if "field" in exclude_condition:
            return self._check_field_exclude(log, exclude_condition)

        if "es_query" in exclude_condition:
            return self._check_es_query(log, exclude_condition["es_query"])

        return False

    def _check_field_exclude(self, log: dict, condition: dict) -> bool:
        """基于字段值的排除检查"""
        field = condition.get("field")
        operator = condition.get("operator", "equals")
        value = condition.get("value")

        log_value = log.get(field)
        if log_value is None:
            return False

        if operator == "equals":
            return str(log_value) == str(value)
        elif operator == "contains":
            return value in str(log_value)
        elif operator == "not_equals":
            return str(log_value) != str(value)
        elif operator == "not_contains":
            return value not in str(log_value)
        return False

    def _check_es_query(self, log: dict, es_query: dict) -> bool:
        """基于ES查询格式的排除检查（简化版）"""
        # 处理 must_not
        must_not = es_query.get("bool", {}).get("must_not", [])
        for condition in must_not:
            if "term" in condition:
                for field, value in condition["term"].items():
                    if str(log.get(field)) == str(value):
                        return True  # 命中排除条件，应跳过
            if "wildcard" in condition:
                for field, pattern in condition["wildcard"].items():
                    log_val = str(log.get(field, ""))
                    # 简单通配符匹配
                    if pattern.endswith("*") and pattern[:-1] in log_val:
                        return True
        return False


# 全局单例
exclude_filter = ExcludeFilter()