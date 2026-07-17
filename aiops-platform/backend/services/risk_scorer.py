"""风险评分引擎"""


class RiskScorer:
    """风险评分引擎"""

    async def score(self, rule_risk: str, severity: int = 0, occurrence_count: int = 1) -> dict:
        """
        综合计算风险评分

        Args:
            rule_risk: 规则风险等级
            severity: 日志严重级别 (0-7)
            occurrence_count: 发生次数
        Returns:
            风险评估结果
        """
        # 基础分
        risk_scores = {"low": 1, "medium": 3, "high": 7, "critical": 10}
        base = risk_scores.get(rule_risk, 3)

        # severity分
        sev_score = max(0, 7 - severity) / 7.0 * 3 if severity > 0 else 0

        # 频次分
        freq_score = min(occurrence_count, 10) / 10.0 * 2

        total = base + sev_score + freq_score
        total = min(total, 10)

        # 确定最终等级
        if total >= 8:
            level = "critical"
        elif total >= 5:
            level = "high"
        elif total >= 3:
            level = "medium"
        else:
            level = "low"

        return {
            "score": round(total, 1),
            "level": level,
            "details": {
                "base_score": base,
                "severity_score": round(sev_score, 1),
                "frequency_score": round(freq_score, 1),
            },
        }


# 全局单例
risk_scorer = RiskScorer()