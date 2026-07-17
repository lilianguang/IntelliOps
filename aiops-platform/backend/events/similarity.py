"""相似度计算"""


class SimilarityCalculator:
    """事件相似度计算"""

    async def calculate_similarity(self, event1: dict, event2: dict) -> float:
        """计算两个事件的相似度（0-1）"""
        score = 0.0
        weights = {"device": 0.4, "type": 0.3, "keyword": 0.3}

        # 设备相似度
        dev1 = event1.get("source_device", "") or event1.get("device_ip", "")
        dev2 = event2.get("source_device", "") or event2.get("device_ip", "")
        if dev1 and dev2 and dev1 == dev2:
            score += weights["device"]

        # 事件类型相似度
        type1 = event1.get("event_type", "")
        type2 = event2.get("event_type", "")
        if type1 and type2 and type1 == type2:
            score += weights["type"]

        # 关键字相似度
        kw1 = event1.get("summary", "")[:50]
        kw2 = event2.get("summary", "")[:50]
        if kw1 and kw2:
            common = len(set(kw1) & set(kw2))
            total = max(len(set(kw1)), len(set(kw2)))
            if total > 0:
                score += weights["keyword"] * (common / total)

        return min(score, 1.0)


# 全局单例
similarity_calculator = SimilarityCalculator()