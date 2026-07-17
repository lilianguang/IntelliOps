"""定时调度器 - 管理所有技能的定时扫描任务"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from scanner.scanner import scan_skill
from netinsight.scanner import scan_configs
from config.settings import settings
from core.db import async_session_factory
from models.skill import Skill
from sqlalchemy import select


class ScanScheduler:
    """定时扫描调度器"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    async def start(self):
        """启动调度器"""
        # 加载所有启用的技能
        async with async_session_factory() as session:
            result = await session.execute(
                select(Skill).where(Skill.enabled == 1)
            )
            skills = result.scalars().all()

        for skill in skills:
            self.scheduler.add_job(
                scan_skill,
                "interval",
                seconds=skill.scan_interval_sec,
                args=[skill.id],
                id=f"scan_{skill.id}",
                replace_existing=True,
                misfire_grace_time=30,
            )
            print(f"[调度器] 已注册扫描任务: {skill.skill_name} (间隔{skill.scan_interval_sec}秒)")

        # 注册网络洞察配置同步任务（每天从只读源目录同步到工作区）
        if settings.NET_CONFIG_SCAN_INTERVAL > 0:
            self.scheduler.add_job(
                scan_configs,
                "interval",
                seconds=settings.NET_CONFIG_SCAN_INTERVAL,
                id="netinsight_config_sync",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
            print(f"[调度器] 已注册网络洞察配置同步任务 (间隔 {settings.NET_CONFIG_SCAN_INTERVAL} 秒)")

        self.scheduler.start()
        print(f"[调度器] 已启动，共 {len(skills)} 个技能扫描任务 + 1 个配置同步任务")

    async def stop(self):
        """停止调度器"""
        self.scheduler.shutdown(wait=False)
        print("[调度器] 已停止")

    async def reload(self):
        """重新加载调度任务（配置变更时调用）"""
        self.scheduler.remove_all_jobs()
        await self.start()


# 全局单例
scan_scheduler = ScanScheduler()