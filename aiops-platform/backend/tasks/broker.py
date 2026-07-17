"""Redis任务队列"""

from core.redis_client import redis_client
import json


class TaskBroker:
    """Redis任务队列"""

    TASK_QUEUE = "aiops:tasks:queue"
    TASK_RESULT_PREFIX = "aiops:tasks:result:"

    async def push_task(self, task_data: dict):
        """推送任务到队列"""
        await redis_client.push_task(self.TASK_QUEUE, task_data)

    async def pop_task(self, timeout: int = 5) -> dict:
        """从队列获取任务"""
        return await redis_client.pop_task(self.TASK_QUEUE, timeout)

    async def save_result(self, task_id: str, result: dict, ttl: int = 3600):
        """保存任务结果"""
        await redis_client.set(
            f"{self.TASK_RESULT_PREFIX}{task_id}",
            result,
            ttl=ttl,
        )

    async def get_result(self, task_id: str) -> dict:
        """获取任务结果"""
        data = await redis_client.get(f"{self.TASK_RESULT_PREFIX}{task_id}")
        return json.loads(data) if data else None


# 全局单例
task_broker = TaskBroker()