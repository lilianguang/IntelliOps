"""规则加载器 - 从MySQL加载规则，缓存到Redis"""

from typing import List, Optional
import json
from models.rule import Rule, RuleType
from core.db import async_session_factory
from core.redis_client import redis_client
from config.settings import settings
from sqlalchemy import select


class RuleLoader:
    """规则加载器"""

    async def load_rules(self, skill_id: int) -> List[Rule]:
        """
        加载指定技能的所有启用规则

        缓存策略：Redis Hash，TTL=RULE_CACHE_TTL秒
        """
        # 1. 尝试从Redis缓存读取
        cache_key = f"rules:{skill_id}"
        cached = await redis_client.get(cache_key)
        if cached:
            return self._deserialize(cached)

        # 2. 缓存未命中，从MySQL加载
        async with async_session_factory() as session:
            result = await session.execute(
                select(Rule)
                .where(Rule.skill_id == skill_id, Rule.enabled == 1)
                .order_by(Rule.priority)
            )
            rules = result.scalars().all()

        # 3. 写入缓存
        if rules:
            await redis_client.set(cache_key, self._serialize(rules), ttl=settings.RULE_CACHE_TTL)

        return list(rules)

    async def load_all_rules(self) -> dict:
        """加载所有技能的规则（按skill_id分组）"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Rule).where(Rule.enabled == 1).order_by(Rule.priority)
            )
            rules = result.scalars().all()

        grouped = {}
        for rule in rules:
            grouped.setdefault(rule.skill_id, []).append(rule)
        return grouped

    async def refresh_cache(self, skill_id: Optional[int] = None):
        """刷新规则缓存"""
        if skill_id:
            cache_key = f"rules:{skill_id}"
            await redis_client.delete(cache_key)
            await self.load_rules(skill_id)
        else:
            # 刷新全部
            grouped = await self.load_all_rules()
            for sid, rules in grouped.items():
                cache_key = f"rules:{sid}"
                await redis_client.set(cache_key, self._serialize(rules), ttl=settings.RULE_CACHE_TTL)

    def _serialize(self, rules: List[Rule]) -> str:
        """序列化规则列表"""
        data = []
        for r in rules:
            data.append({
                "id": r.id,
                "rule_name": r.rule_name,
                "skill_id": r.skill_id,
                "rule_type": r.rule_type.value if hasattr(r.rule_type, 'value') else r.rule_type,
                "match_condition": r.match_condition,
                "exclude_condition": r.exclude_condition,
                "risk_level": r.risk_level.value if hasattr(r.risk_level, 'value') else r.risk_level,
                "action_config": r.action_config,
                "priority": r.priority,
            })
        return json.dumps(data, default=str)

    def _deserialize(self, data: str) -> List:
        """反序列化为支持属性访问的对象（兼容 Rule ORM 的 .attr 语法）"""
        from types import SimpleNamespace
        items = json.loads(data)
        return [SimpleNamespace(**item) for item in items]


# 全局单例
rule_loader = RuleLoader()