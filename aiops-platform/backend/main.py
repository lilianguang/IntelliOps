"""AIOPS 智能运维平台 - 应用启动入口"""

import uuid

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import bcrypt as _bcrypt

from core.request_context import set_request_id

from config.settings import settings
from core.db import init_db, close_db, async_session_factory
from core.es_client import es_client
from core.llm_client import llm_client
from core.redis_client import redis_client
from models.user import User
from scanner.scheduler import scan_scheduler
from sqlalchemy import select

# 创建应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestIdMiddleware:
    """为每个请求分配/透传 request_id，支持从 X-Request-ID 请求头读取。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = ""
        if b"x-request-id" in headers:
            request_id = headers[b"x-request-id"].decode("utf-8", errors="ignore")
        if not request_id:
            request_id = str(uuid.uuid4())
        set_request_id(request_id)

        await self.app(scope, receive, send)


app.add_middleware(RequestIdMiddleware)


@app.on_event("startup")
async def startup():
    """应用启动事件"""
    await init_db()
    
    # 自动创建或修复默认管理员
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.username == "admin")
            )
            user = result.scalar_one_or_none()
            if user:
                print("[AIOPS] 管理员账号已存在")
            else:
                salt = _bcrypt.gensalt()
                admin = User(
                    username="admin",
                    password_hash=_bcrypt.hashpw("admin123".encode(), salt).decode(),
                    display_name="系统管理员",
                    role="admin",
                    enabled=1,
                )
                session.add(admin)
                await session.commit()
                print("[AIOPS] 已创建默认管理员: admin / admin123")
    except Exception as e:
        print(f"[AIOPS] 管理员创建跳过: {e}")
    
    # 启动定时扫描调度器
    await scan_scheduler.start()
    
    print(f"[AIOPS] {settings.APP_NAME} v{settings.APP_VERSION} 启动成功")
    print(f"[AIOPS] ES: {settings.ES_HOSTS}")
    print(f"[AIOPS] Redis: {settings.REDIS_URL}")


@app.on_event("shutdown")
async def shutdown():
    """应用关闭事件"""
    await scan_scheduler.stop()
    await close_db()
    await es_client.close()
    await redis_client.close()
    print("[AIOPS] 服务已关闭")


# ===== 路由注册 =====
from api.health import router as health_router
from api.auth import router as auth_router
from api.skills import router as skills_router
from api.configs import router as configs_router
from api.chat import router as chat_router
from api.conversations import router as conversations_router
from api.events import router as events_router
from api.dashboard import router as dashboard_router
from api.users import router as users_router
from api.prometheus import router as prometheus_router
from api.cmdb import router as cmdb_router
from api.netinsight import router as netinsight_router
from api.logical import router as logical_router
from api.system import router as system_router

app.include_router(health_router, prefix="/api/ai", tags=["健康检查"])
app.include_router(auth_router, prefix="/api/auth", tags=["认证"])
app.include_router(skills_router, prefix="/api/ai", tags=["技能管理"])
app.include_router(configs_router, prefix="/api/ai/config", tags=["配置中心"])
app.include_router(chat_router, prefix="/api/ai", tags=["对话"])
app.include_router(conversations_router, prefix="/api/ai", tags=["对话历史"])
app.include_router(events_router, prefix="/api/ai", tags=["事件中心"])
app.include_router(dashboard_router, prefix="/api/ai", tags=["仪表盘"])
app.include_router(users_router, prefix="/api/users", tags=["用户管理"])
app.include_router(prometheus_router, prefix="/api/ai", tags=["Prometheus监控"])
app.include_router(cmdb_router, prefix="/api/ai", tags=["CMDB IT资源管理"])
app.include_router(netinsight_router, prefix="/api/ai", tags=["网络洞察"])
app.include_router(logical_router, prefix="/api/ai", tags=["逻辑资源层"])
app.include_router(system_router, prefix="/api/ai", tags=["系统管理"])


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )