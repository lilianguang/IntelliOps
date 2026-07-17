"""钉钉机器人通知"""

from alerts.base import BaseNotifier
import httpx
import time
import hmac
import hashlib
import base64
import urllib.parse


def _sign_url(webhook_url: str, secret: str) -> str:
    """钉钉签名：将 timestamp + sign 追加到 URL 中"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    separator = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}{separator}timestamp={timestamp}&sign={sign}"


class DingTalkNotifier(BaseNotifier):
    """钉钉机器人通知"""

    def __init__(self, config: dict):
        self.webhook_url = config.get("webhook_url", "")
        self.secret = config.get("secret", "")

    async def send(self, message: str) -> bool:
        """发送钉钉消息"""
        if not self.webhook_url:
            return False

        # 如果配置了加密密钥，生成签名 URL
        url = self.webhook_url
        if self.secret:
            url = _sign_url(url, self.secret)

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "AIOPS 智能告警",
                "text": message,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(url, json=payload)
                data = response.json() if response.status_code == 200 else {}
                errcode = data.get("errcode", -1)
                errmsg = data.get("errmsg", "")
                print(f"[钉钉告警] HTTP状态={response.status_code}, errcode={errcode}, errmsg={errmsg}")
                return response.status_code == 200 and errcode == 0
        except Exception as e:
            print(f"[钉钉告警失败] {str(e)}")
            return False