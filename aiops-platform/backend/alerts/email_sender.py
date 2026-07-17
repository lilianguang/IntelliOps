"""邮件通知"""

from alerts.base import BaseNotifier
import smtplib
from email.mime.text import MIMEText


class EmailNotifier(BaseNotifier):
    """邮件通知"""

    def __init__(self, config: dict):
        self.smtp_host = config.get("smtp_host", "")
        self.smtp_port = config.get("smtp_port", 465)
        self.smtp_user = config.get("smtp_user", "")
        self.smtp_pass = config.get("smtp_pass", "")
        self.from_addr = config.get("from_addr", "")
        self.to_addrs = config.get("to_addrs", [])
        self.use_ssl = config.get("use_ssl", True)

    async def send(self, message: str) -> bool:
        """发送邮件"""
        if not all([self.smtp_host, self.from_addr, self.to_addrs]):
            return False

        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = "AIOPS 智能告警通知"
        msg["From"] = self.from_addr
        msg["To"] = ",".join(self.to_addrs) if isinstance(self.to_addrs, list) else self.to_addrs

        try:
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)

            if self.smtp_user and self.smtp_pass:
                server.login(self.smtp_user, self.smtp_pass)

            server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            print(f"[邮件告警失败] {str(e)}")
            return False