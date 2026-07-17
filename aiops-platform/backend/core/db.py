"""MySQL ORM 异步数据库会话管理"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config.settings import settings


# 创建异步引擎
# 创建异步引擎
engine = create_async_engine(
    settings.MYSQL_DSN,
    pool_size=settings.MYSQL_POOL_SIZE,
    echo=settings.DEBUG,
    connect_args={"charset": "utf8mb4"},
)
# 会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """所有模型的基类"""
    pass


async def get_session() -> AsyncSession:
    """获取异步数据库会话"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """初始化数据库连接（应用启动时调用）"""
    # 导入所有模型以确保 metadata 包含全部表
    import models.skill  # noqa
    import models.datasource  # noqa
    import models.llm_config  # noqa
    import models.alert_channel  # noqa
    import models.user  # noqa
    import models.conversation  # noqa
    import models.report  # noqa
    import models.event  # noqa
    import models.rule  # noqa
    import models.audit_log  # noqa
    import models.keyword  # noqa
    import models.cmdb  # noqa
    import models.netinsight  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """关闭数据库连接（应用关闭时调用）"""
    await engine.dispose()