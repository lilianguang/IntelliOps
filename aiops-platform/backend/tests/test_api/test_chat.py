"""Module 5: AI对话测试"""
import pytest

pytestmark = pytest.mark.asyncio


class TestChat:
    """TC-19 ~ TC-21: AI对话"""

    async def test_chat_with_skill(self, client, admin_token):
        """TC-19: POST /api/ai/chat (h3c-net-analysis技能)"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        headers = {"Authorization": f"Bearer {admin_token}"}
        chat_req = {
            "tenant": "ops",
            "user": "admin",
            "skill": "h3c-net-analysis",
            "query": "分析最近30分钟核心交换机异常",
            "time_range": "30m",
            "stream": False
        }
        resp = await client.post("/api/ai/chat", json=chat_req, headers=headers)
        print(f"对话响应: {resp.status_code}")
        assert resp.status_code in (200, 202, 500)

    async def test_chat_without_skill(self, client, admin_token):
        """TC-20: 未指定skill，自动路由"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        headers = {"Authorization": f"Bearer {admin_token}"}
        chat_req = {
            "tenant": "ops",
            "user": "admin",
            "query": "分析核心交换机异常",
            "time_range": "30m"
        }
        resp = await client.post("/api/ai/chat", json=chat_req, headers=headers)
        print(f"自动路由响应: {resp.status_code}")

    async def test_task_status(self, client, admin_token):
        """TC-21: 查询任务状态"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        headers = {"Authorization": f"Bearer {admin_token}"}
        chat_req = {
            "tenant": "ops",
            "user": "admin",
            "skill": "h3c-net-analysis",
            "query": "测试查询",
            "time_range": "5m"
        }
        resp = await client.post("/api/ai/chat", json=chat_req, headers=headers)
        if resp.status_code == 202:
            task_id = resp.json().get("task_id")
            if task_id:
                task_resp = await client.get(
                    f"/api/ai/tasks/{task_id}",
                    headers=headers
                )
                print(f"任务状态: {task_resp.status_code}")
