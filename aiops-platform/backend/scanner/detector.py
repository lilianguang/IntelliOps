"""异常检测模块（可选）"""


class AnomalyDetector:
    """AI异常检测（基于统计规则）"""

    async def detect(self, logs: list, threshold: float = 0.7) -> list:
        """
        检测异常日志

        简易实现：基于频率和关键词的异常检测
        """
        anomalies = []
        if not logs:
            return anomalies

        # 统计日志级别分布
        severity_counts = {}
        for log in logs:
            sev = log.get("severity", "0")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        # 检测异常
        for log in logs:
            score = 0

            # 高严重级别
            try:
                sev = int(log.get("severity", 0))
                if sev <= 3:
                    score += 0.5
            except ValueError:
                pass

            # 异常关键词
            msg = str(log.get("message", "")).lower()
            keywords = ["error", "fail", "down", "shutdown", "critical"]
            for kw in keywords:
                if kw in msg:
                    score += 0.3

            if score >= threshold:
                anomalies.append({
                    "log": log,
                    "anomaly_score": score,
                    "reason": f"异常评分 {score:.2f} >= 阈值 {threshold:.2f}",
                })

        return anomalies


# 全局单例
anomaly_detector = AnomalyDetector()