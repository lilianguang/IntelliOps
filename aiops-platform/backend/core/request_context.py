"""请求上下文工具

提供基于 contextvars 的 request_id 透传能力，便于错误日志链路追踪。
"""

import contextvars
from uuid import uuid4

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def get_request_id() -> str:
    """获取当前请求 ID；若未设置则自动生成一个 UUID。"""
    req_id = request_id_ctx.get("")
    if not req_id:
        req_id = str(uuid4())
        request_id_ctx.set(req_id)
    return req_id


def set_request_id(request_id: str) -> None:
    """设置当前请求 ID。"""
    request_id_ctx.set(request_id)
