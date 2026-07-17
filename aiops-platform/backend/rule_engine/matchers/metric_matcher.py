"""Prometheus 指标阈值匹配器 - 用于 metric_threshold 规则类型"""


class MetricMatcher:
    """指标阈值匹配器

    支持单条件（向后兼容）和多条件组合：
    - 单条件: {"metric": "cpu_usage", "operator": ">", "value": 90, "instance_filter": "10.0.*"}
    - 多条件: {"logic": "OR", "conditions": [{...}, {...}]}

    指标名应匹配技能 query_config.promql_templates 中定义的 name 字段，
    例如："接口光衰"、"政务外网接口入方向流量"、"cpu_usage" 等。
    """

    OPERATORS = {
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        "==": lambda a, b: abs(a - b) < 0.001,
        "!=": lambda a, b: abs(a - b) >= 0.001,
    }

    async def match(self, data: dict, condition: dict) -> bool:
        """匹配指标数据是否满足阈值条件"""
        conditions = condition.get("conditions")
        if isinstance(conditions, list) and len(conditions) > 0:
            logic = condition.get("logic", "OR").upper()
            results = [self._match_single(data, c) for c in conditions]
            if logic == "AND":
                return all(results)
            return any(results)

        # 向后兼容：扁平单条件
        return self._match_single(data, condition)

    def _match_single(self, data: dict, condition: dict) -> bool:
        """单个指标条件匹配"""
        # 1. 检查指标名是否匹配
        target_metric = condition.get("metric", "")
        data_metric = data.get("metric_name", "")
        if target_metric and data_metric != target_metric:
            return False

        # 2. 可选：实例过滤
        instance_filter = condition.get("instance_filter", "")
        if instance_filter:
            instance = data.get("instance", "")
            if not self._match_wildcard(instance, instance_filter):
                return False

        # 3. 数值比较
        metric_value = data.get("metric_value")
        if metric_value is None:
            return False

        try:
            metric_value = float(metric_value)
        except (TypeError, ValueError):
            return False

        operator = condition.get("operator", ">")
        threshold = condition.get("value", 0)
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            return False

        compare_fn = self.OPERATORS.get(operator)
        if not compare_fn:
            return False

        return compare_fn(metric_value, threshold)

    def _match_wildcard(self, text: str, pattern: str) -> bool:
        """简单通配符匹配（支持 * 和 ?）"""
        import fnmatch
        return fnmatch.fnmatch(text, pattern)


# 全局单例
metric_matcher = MetricMatcher()
