"""告警通知分发器"""

from typing import List
from core.db import async_session_factory
from models.alert_channel import AlertChannel
from sqlalchemy import select


class Notifier:
    """告警通知分发器"""

    async def notify_all(self, message: str) -> List[dict]:
        """
        向所有已启用的告警渠道发送通知

        Args:
            message: 告警消息文本
        Returns:
            各渠道发送结果列表
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(AlertChannel).where(AlertChannel.enabled == 1)
            )
            channels = result.scalars().all()

        return await self._send_to_channels(message, channels)

    async def notify_by_channels(self, message: str, channel_ids: List[int]) -> List[dict]:
        """
        向指定ID的告警渠道发送通知（忽略未启用或不存在渠道）

        Args:
            message: 告警消息文本
            channel_ids: 告警渠道ID列表
        Returns:
            各渠道发送结果列表
        """
        if not channel_ids:
            return []
        async with async_session_factory() as session:
            result = await session.execute(
                select(AlertChannel).where(
                    AlertChannel.id.in_(channel_ids),
                    AlertChannel.enabled == 1
                )
            )
            channels = result.scalars().all()

        return await self._send_to_channels(message, channels)

    async def _send_to_channels(self, message: str, channels: List[AlertChannel]) -> List[dict]:
        """内部：向渠道列表发送消息"""
        results = []
        for channel in channels:
            try:
                print(f"[告警通知] 开始向渠道 '{channel.name}'({channel.channel_type}) 发送消息")
                if channel.channel_type == "dingtalk":
                    from alerts.dingtalk import DingTalkNotifier
                    notifier = DingTalkNotifier(channel.config)
                elif channel.channel_type == "email":
                    from alerts.email_sender import EmailNotifier
                    notifier = EmailNotifier(channel.config)
                elif channel.channel_type == "webhook":
                    from alerts.webhook import WebhookNotifier
                    notifier = WebhookNotifier(channel.config)
                else:
                    print(f"[告警通知] 未知渠道类型: {channel.channel_type}")
                    continue

                success = await notifier.send(message)
                print(f"[告警通知] 渠道 '{channel.name}'({channel.channel_type}) 发送结果: {success}")
                results.append({
                    "channel": channel.name,
                    "type": channel.channel_type,
                    "success": success,
                })
            except Exception as e:
                print(f"[告警通知] 渠道 '{channel.name}'({channel.channel_type}) 发送异常: {e}")
                results.append({
                    "channel": channel.name,
                    "type": channel.channel_type,
                    "success": False,
                    "error": str(e),
                })

        return results


# 全局单例
notifier = Notifier()