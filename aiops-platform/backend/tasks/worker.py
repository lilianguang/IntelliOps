"""异步Worker - 处理任务队列中的任务"""

from tasks.broker import task_broker
from skills.engine import skill_engine
import asyncio


class TaskWorker:
    """异步Worker"""

    async def start(self):
        """启动Worker（持续轮询任务）"""
        print("[Worker] 启动，等待任务...")
        while True:
            try:
                task_data = await task_broker.pop_task(timeout=5)
                if task_data:
                    await self._process_task(task_data)
            except Exception as e:
                print(f"[Worker] 错误: {str(e)}")
                await asyncio.sleep(1)

    async def _process_task(self, task_data: dict):
        """处理单个任务"""
        task_id = task_data.get("task_id")
        skill = task_data.get("skill")
        query = task_data.get("query", "")
        time_range = task_data.get("time_range", "30m")

        print(f"[Worker] 处理任务 {task_id}: skill={skill}")

        try:
            # 更新状态为处理中
            await task_broker.save_result(task_id, {"status": "processing"})

            # 执行技能
            result = await skill_engine.execute(skill, query, time_range)

            # 保存结果
            result["status"] = "completed"
            await task_broker.save_result(task_id, result)
            print(f"[Worker] 任务 {task_id} 完成")

        except Exception as e:
            error_result = {"status": "failed", "error": str(e)}
            await task_broker.save_result(task_id, error_result)
            print(f"[Worker] 任务 {task_id} 失败: {str(e)}")


# 全局单例
task_worker = TaskWorker()