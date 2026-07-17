"""一次性迁移脚本：为 skills 表添加 field_schema 列并预填充字段说明"""

import asyncio
import json
from sqlalchemy import select, text
from core.db import async_session_factory
from models.skill import Skill

# Nginx 访问日志字段说明
NGINX_FIELDS = [
    {"name": "@timestamp", "type": "date", "desc": "日志时间戳", "example": "2026-06-25T10:30:00.000Z"},
    {"name": "hostname", "type": "keyword", "desc": "服务器名称", "example": "ywtbjzdl1"},
    {"name": "ip", "type": "ip", "desc": "真实源IP（地址透传后，未拿到为空）", "example": "192.66.1.2"},
    {"name": "client", "type": "ip", "desc": "登录源IP/客户端IP", "example": "192.66.15.24"},
    {"name": "request_method", "type": "keyword", "desc": "HTTP请求方法", "example": "GET"},
    {"name": "domain", "type": "keyword", "desc": "访问域名", "example": "buyer.jgj.egov.cn"},
    {"name": "referer", "type": "text", "desc": "请求来源URL", "example": "http://buyer.jgj.egov.cn/store/product"},
    {"name": "request", "type": "text", "desc": "请求路径", "example": "/v3/frontLogin/front/oauth/token"},
    {"name": "size", "type": "long", "desc": "响应字节数", "example": "231"},
    {"name": "status", "type": "keyword", "desc": "HTTP状态码", "example": "200"},
    {"name": "responsetime", "type": "float", "desc": "请求总响应时间(秒)", "example": "0.01"},
    {"name": "upstreamtime", "type": "float", "desc": "Nginx到后端服务器响应时间(秒)", "example": "0.001"},
    {"name": "upstreamaddr", "type": "text", "desc": "后端服务器IP:端口", "example": "127.0.0.1:8500"},
    {"name": "http_user_agent", "type": "text", "desc": "请求客户端类型(UA)", "example": "Mozilla/5.0 (Windows NT 6.1)"},
    {"name": "log_type", "type": "keyword", "desc": "业务类型标识", "example": "nginx-综合配送管理平台"},
    {"name": "geo_client", "type": "object", "desc": "客户端IP的GeoIP地理信息（国家/城市/坐标）", "example": '{"ip":"192.66.1.155","country":"丹麦"}'},
    {"name": "geo_ip", "type": "object", "desc": "源IP的GeoIP地理信息", "example": '{"ip":"192.67.1.2","country":"印尼"}'},
    {"name": "geo_location", "type": "geo_point", "desc": "地理位置坐标(lat/lon)", "example": '{"lat":55.7,"lon":12.0}'},
]

# H3C 网络设备日志字段说明
H3C_FIELDS = [
    {"name": "timestamp", "type": "date", "desc": "日志时间", "example": "2026-06-02T02:18:58"},
    {"name": "device_ip", "type": "ip", "desc": "设备IP地址", "example": "192.168.169.11"},
    {"name": "hostname", "type": "keyword", "desc": "设备名称", "example": "B201-M01_HLW_L3SW_S6520X-54QC-EI-01"},
    {"name": "src_ip", "type": "ip", "desc": "登录源IP", "example": "192.168.169.13"},
    {"name": "user", "type": "keyword", "desc": "登录用户名", "example": "jgswy"},
    {"name": "module", "type": "keyword", "desc": "日志模块", "example": "SHELL"},
    {"name": "event_name", "type": "keyword", "desc": "事件名称", "example": "SHELL_CMD"},
    {"name": "command", "type": "text", "desc": "执行的命令内容", "example": "dis ip int br"},
    {"name": "severity", "type": "integer", "desc": "日志级别(0-7)", "example": "6"},
    {"name": "region", "type": "keyword", "desc": "网络区域(int=互联网, gov=政务外网)", "example": "gov"},
    {"name": "message", "type": "text", "desc": "完整日志信息", "example": "-Line=vty0-IPAddr=192.168.169.13-User=jgswy; Command is dis ip int br"},
]

FIELD_MAP = {
    "nginx-access-analysis": NGINX_FIELDS,
    "nginx-business-report": NGINX_FIELDS,
    "h3c-net-analysis": H3C_FIELDS,
}


async def migrate():
    async with async_session_factory() as session:
        # 1. 添加 field_schema 列（如果不存在）
        try:
            await session.execute(text("ALTER TABLE skills ADD COLUMN field_schema TEXT"))
            print("[迁移] 已添加 field_schema 列")
        except Exception:
            print("[迁移] field_schema 列已存在，跳过")

        # 2. 预填充字段说明
        for skill_name, fields in FIELD_MAP.items():
            result = await session.execute(
                select(Skill).where(Skill.skill_name == skill_name)
            )
            skill = result.scalar_one_or_none()
            if skill:
                skill.field_schema = json.dumps(fields, ensure_ascii=False)
                print(f"[迁移] 已填充 {skill_name} 的字段说明 ({len(fields)} 个字段)")
            else:
                print(f"[迁移] 技能 {skill_name} 不存在，跳过")

        await session.commit()
        print("[迁移] 完成")


if __name__ == "__main__":
    asyncio.run(migrate())
