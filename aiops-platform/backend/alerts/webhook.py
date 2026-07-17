"""Webhook通知"""

from alerts.base import BaseNotifier
import httpx


class WebhookNotifier(BaseNotifier):
    """通用Webhook通知"""

    def __init__(self, config: dict):
        self.url = config.get("url", "")
        self.method = config.get("method", "POST")
        self.headers = config.get("headers", {})

    async def send(self, message: str) -> bool:
        """发送Webhook"""
        if not self.url:
            return False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if self.method.upper() == "POST":
                    response = await client.post(
                        self.url,
                        json={"text": message, "msgtype": "markdown"},
                        headers=self.headers,
                    )
                else:
                    response = await client.get(self.url, headers=self.headers)
                return response.status_code == 200
        except Exception as e:
            print(f"[Webhook告警失败] {str(e)}")
            return False