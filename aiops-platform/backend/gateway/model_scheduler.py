"""多模型调度器 - 主备切换/负载均衡"""

from typing import Optional, List, Dict
from models.llm_config import LLMConfig
from core.db import async_session_factory
from sqlalchemy import select


class ModelScheduler:
    """多模型调度器"""

    async def get_model(self, preferred_model: Optional[str] = None) -> Optional[Dict]:
        """
        获取要使用的模型配置

        策略：
        1. 指定模型 → 直接返回
        2. 未指定 → 按优先级返回主模型
        3. 主模型不可用 → 切换备用
        """
        configs = await self._load_configs()

        if not configs:
            return None

        # 如果指定了模型名称，按名称匹配
        if preferred_model:
            for cfg in configs:
                if cfg["model_name"] == preferred_model and cfg["enabled"]:
                    return cfg

        # 按优先级返回（priority=0 为主模型）
        configs.sort(key=lambda x: x["priority"])
        return configs[0] if configs else None

    async def get_available_models(self) -> List[Dict]:
        """获取所有可用模型"""
        return await self._load_configs()

    async def _load_configs(self) -> List[Dict]:
        """从数据库加载模型配置"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(LLMConfig).where(LLMConfig.enabled == 1)
            )
            configs = result.scalars().all()
            return [
                {
                    "id": c.id,
                    "name": c.name,
                    "model_name": c.model_name,
                    "api_base": c.api_base,
                    "api_key": c.api_key,
                    "temperature": c.temperature,
                    "priority": c.priority,
                    "enabled": c.enabled,
                }
                for c in configs
            ]


# 全局单例
model_scheduler = ModelScheduler()