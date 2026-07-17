"""告警风暴控制器 - v3.0 混合告警策略

策略：
- 正常（窗口内未超阈值）：每次命中立即发送
- 触达阈值：标记抑制，启动汇总定时器
- 抑制中：只计数，不发送
- 汇总时间到：发送汇总告警，重置
"""

from typing import Optional, List
from core.redis_client import redis_client
from core.db import async_session_factory
from models.rule import Rule, AlertStormConfig, AlertStormEvent
from sqlalchemy import select
from datetime import datetime
import hashlib
import json


class StormController:
    """告警风暴控制器"""

    async def evaluate_and_alert(
        self,
        rule: Rule,
        log: dict,
        analysis: Optional[str],
        alert_fields: list,
        alert_type: str,
    ) -> dict:
        """
        评估风暴状态并决定告警方式

        Returns:
            {"alert_type": "immediate"|"digest"|"suppressed", "message": ...}
        """
        from rule_engine.executor import action_executor  # 延迟导入，避免循环引用

        # 1. 生成风暴指纹
        fingerprint = self._generate_fingerprint(rule, log)

        # 2. 获取风暴配置
        storm_config = await self._get_storm_config(rule.skill_id, rule.id)

        # 3. 如果没有风暴配置，直接告警
        if not storm_config:
            return await action_executor.send_alert(rule, log, analysis, alert_fields, alert_type)

        # 4. 检查风暴状态
        counter_key = f"storm:{rule.id}:{fingerprint}"
        count = await redis_client.incr(counter_key, ttl=storm_config.window_minutes * 60)

        if count == 1:
            # 首次出现，记录风暴事件
            await self._record_storm_event(rule.id, fingerprint)

        if count <= storm_config.max_count:
            # 正常：立即告警
            return await action_executor.send_alert(rule, log, analysis, alert_fields, "immediate")
        elif count == storm_config.max_count + 1:
            # 刚触达阈值：标记抑制，发送最后一条告警，启动汇总
            await self._mark_suppressed(rule.id, fingerprint)
            return {
                "alert_type": "digest",
                "message": f"[风暴抑制] 规则 {rule.rule_name} 在{storm_config.window_minutes}分钟内触发超过{storm_config.max_count}次，后续告警将汇总发送",
                "risk_level": rule.risk_level.value if hasattr(rule.risk_level, 'value') else rule.risk_level,
                "suppressed": True,
            }
        else:
            # 已抑制：只更新计数
            await self._update_storm_count(rule.id, fingerprint, count)
            return {
                "alert_type": "suppressed",
                "message": f"[已抑制] 规则 {rule.rule_name} 告警已被风暴抑制（累计{count}次）",
                "risk_level": rule.risk_level.value if hasattr(rule.risk_level, 'value') else rule.risk_level,
                "suppressed": True,
            }

    def _generate_fingerprint(self, rule: Rule, log: dict) -> str:
        """生成风暴指纹"""
        device_ip = log.get("device_ip", "") or log.get("client", "") or log.get("domain", "")
        raw = f"{rule.id}:{device_ip}:{rule.rule_type}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def _get_storm_config(self, skill_id: int, rule_id: int) -> Optional[AlertStormConfig]:
        """获取风暴配置"""
        async with async_session_factory() as session:
            # 先查规则级别配置
            result = await session.execute(
                select(AlertStormConfig)
                .where(AlertStormConfig.rule_id == rule_id, AlertStormConfig.enabled == 1)
            )
            config = result.scalar_one_or_none()
            if config:
                return config

            # 再查技能级别配置
            result = await session.execute(
                select(AlertStormConfig)
                .where(AlertStormConfig.skill_id == skill_id, AlertStormConfig.rule_id.is_(None), AlertStormConfig.enabled == 1)
            )
            return result.scalar_one_or_none()

    async def _record_storm_event(self, rule_id: int, fingerprint: str):
        """记录风暴事件"""
        async with async_session_factory() as session:
            event = AlertStormEvent(
                rule_id=rule_id,
                fingerprint=fingerprint,
                first_seen=datetime.now(),
                last_seen=datetime.now(),
                count=1,
            )
            session.add(event)
            await session.commit()

    async def _mark_suppressed(self, rule_id: int, fingerprint: str):
        """标记为抑制状态"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(AlertStormEvent)
                .where(AlertStormEvent.rule_id == rule_id, AlertStormEvent.fingerprint == fingerprint)
                .order_by(AlertStormEvent.id.desc())
            )
            event = result.scalar_one_or_none()
            if event:
                event.suppressed = 1
                await session.commit()

    async def _update_storm_count(self, rule_id: int, fingerprint: str, count: int):
        """更新风暴计数"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(AlertStormEvent)
                .where(AlertStormEvent.rule_id == rule_id, AlertStormEvent.fingerprint == fingerprint)
                .order_by(AlertStormEvent.id.desc())
            )
            event = result.scalar_one_or_none()
            if event:
                event.count = count
                event.last_seen = datetime.now()
                await session.commit()


# 全局单例
storm_controller = StormController()