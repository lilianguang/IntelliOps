"""告警通知基类"""

from abc import ABC, abstractmethod


class BaseNotifier(ABC):
    """告警通知基类 - 新增渠道只需继承此类"""

    @abstractmethod
    async def send(self, message: str) -> bool:
        """发送告警通知"""
        pass