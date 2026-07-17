"""ES复杂查询匹配器 - dangerous_command 等复杂规则"""

import re


class ESQueryMatcher:
    """ES查询匹配器：在Python层面模拟ES查询DSL的简化匹配"""

    async def match(self, log: dict, es_query: dict) -> bool:
        """
        检查日志是否匹配ES查询条件

        支持的DSL操作：
        - bool.must
        - bool.should
        - bool.filter.must_not
        - term
        - wildcard
        - range
        """
        if "bool" not in es_query:
            return False

        bool_query = es_query["bool"]

        # 处理 must（必须匹配）
        must = bool_query.get("must", [])
        if must:
            for condition in must:
                if not self._match_condition(log, condition):
                    return False

        # 处理 should（至少匹配一个）
        should = bool_query.get("should", [])
        if should:
            should_match = False
            for condition in should:
                if self._match_condition(log, condition):
                    should_match = True
                    break
            if not should_match:
                return False

        # 处理 must_not（不能匹配）
        must_not = bool_query.get("must_not", [])
        filter_must_not = bool_query.get("filter", [{}])[0].get("bool", {}).get("must_not", []) if bool_query.get("filter") else []
        all_must_not = must_not + filter_must_not
        if all_must_not:
            for condition in all_must_not:
                if self._match_condition(log, condition):
                    return False

        return True

    def _match_condition(self, log: dict, condition: dict) -> bool:
        """匹配单个条件"""
        if "term" in condition:
            for field, value in condition["term"].items():
                return str(log.get(field, "")) == str(value)

        if "wildcard" in condition:
            for field, pattern in condition["wildcard"].items():
                log_val = str(log.get(field, ""))
                # 将 wildcard 模式转为正则
                regex = re.escape(pattern).replace(r"\*", ".*")
                return bool(re.match(regex, log_val))

        if "range" in condition:
            for field, ranges in condition["range"].items():
                log_val = log.get(field)
                if log_val is None:
                    return False
                try:
                    log_num = float(log_val)
                    for op, val in ranges.items():
                        if op == "gte" and log_num < float(val):
                            return False
                        if op == "lte" and log_num > float(val):
                            return False
                        if op == "gt" and log_num <= float(val):
                            return False
                        if op == "lt" and log_num >= float(val):
                            return False
                    return True
                except (ValueError, TypeError):
                    return False

        if "bool" in condition:
            # 递归处理嵌套 bool
            return self._match_bool(log, condition["bool"])

        return False

    def _match_bool(self, log: dict, bool_query: dict) -> bool:
        """匹配布尔查询"""
        # should（至少匹配一个）
        should = bool_query.get("should", [])
        if should:
            for condition in should:
                if self._match_condition(log, condition):
                    return True
            return False

        # must（全部匹配）
        must = bool_query.get("must", [])
        if must:
            for condition in must:
                if not self._match_condition(log, condition):
                    return False
            return True

        return True


# 全局单例
es_query_matcher = ESQueryMatcher()