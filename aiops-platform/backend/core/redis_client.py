"""Redis 异步客户端

用于：任务队列、缓存、会话管理、风暴计数器。
"""

from typing import Optional, Any
import json
from redis.asyncio import Redis as AsyncRedis
from config.settings import settings


class RedisClient:
    """Redis客户端封装"""

    def __init__(self):
        self._redis: Optional[AsyncRedis] = None

    async def _get_conn(self) -> AsyncRedis:
        """获取或创建Redis连接"""
        if self._redis is None:
            self._redis = AsyncRedis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
        return self._redis

    # ---- 通用操作 ----
    async def set(self, key: str, value: Any, ttl: int = 0):
        """设置值"""
        r = await self._get_conn()
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        if ttl > 0:
            await r.setex(key, ttl, value)
        else:
            await r.set(key, value)

    async def delete(self, key: str):
        """删除键"""
        r = await self._get_conn()
        await r.delete(key)

    async def get(self, key: str) -> Optional[str]:
        """获取值"""
        r = await self._get_conn()
        return await r.get(key)

    async def delete(self, key: str):
        """删除键"""
        r = await self._get_conn()
        await r.delete(key)

    # ---- 任务队列 ----
    async def push_task(self, queue: str, task_data: dict):
        """向队列推送任务"""
        r = await self._get_conn()
        await r.lpush(queue, json.dumps(task_data))

    async def pop_task(self, queue: str, timeout: int = 5) -> Optional[dict]:
        """从队列获取任务（阻塞）"""
        r = await self._get_conn()
        result = await r.brpop(queue, timeout=timeout)
        if result:
            _, data = result
            return json.loads(data)
        return None

    # ---- 计数器（风暴抑制用） ----
    async def incr(self, key: str, ttl: int = 300) -> int:
        """自增并设置过期时间"""
        r = await self._get_conn()
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, ttl)
        return count

    async def get_count(self, key: str) -> int:
        """获取当前计数"""
        r = await self._get_conn()
        val = await r.get(key)
        return int(val) if val else 0

    # ---- Hash操作 ----
    async def hset(self, key: str, field: str, value: Any):
        """设置Hash字段"""
        r = await self._get_conn()
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        await r.hset(key, field, value)

    async def hget(self, key: str, field: str) -> Optional[str]:
        """获取Hash字段"""
        r = await self._get_conn()
        return await r.hget(key, field)

    async def hgetall(self, key: str) -> dict:
        """获取所有Hash字段"""
        r = await self._get_conn()
        return await r.hgetall(key)

    async def expire(self, key: str, ttl: int):
        """设置过期时间"""
        r = await self._get_conn()
        await r.expire(key, ttl)

    async def close(self):
        """关闭连接"""
        if self._redis:
            await self._redis.close()
            self._redis = None


# 全局单例
redis_client = RedisClient()