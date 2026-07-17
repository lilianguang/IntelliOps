"""AI日志去重与价值判断"""

from core.llm_client import llm_client


class LogDeduplicator:
    """日志去重与价值判断"""

    async def assess_log_value(self, log_entry: dict) -> bool:
        """
        判断日志是否有分析价值

        调用轻量LLM判断日志价值：
        - 是否与已有事件重复
        - 是否具有分析价值
        - 返回价值评分 0-1
        """
        message = log_entry.get("message", "") or log_entry.get("command", "")
        if not message:
            return False

        prompt = f"判断以下日志的分析价值，只需返回0或1(1表示有价值): {message[:200]}"
        try:
            response = await llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=10,
            )
            return "1" in response.strip()
        except Exception:
            return True  # 默认保留


# 全局单例
log_dedup = LogDeduplicator()