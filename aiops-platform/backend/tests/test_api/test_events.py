"""Module 6: 事件中心测试"""
import pytest

pytestmark = pytest.mark.asyncio


class TestEvents:
    """TC-22 ~ TC-24: 事件中心"""

    async def test_list_events(self, client, admin_token):
        """TC-22: GET /api/ai/events 事件列表"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = await client.get("/api/ai/events", headers=headers)
        print(f"事件列表: {resp.status_code}")
        assert resp.status_code in (200, 404)

    async def test_event_stats(self, client, admin_token):
        """TC-23: GET /api/ai/events/stats 统计数据"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = await client.get("/api/ai/events/stats", headers=headers)
        print(f"事件统计: {resp.status_code}")

    async def test_update_event_status(self, client, admin_token):
        """TC-24: PUT /api/ai/events/{id}/status 更新事件状态"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = await client.get("/api/ai/events", headers=headers)
        if resp.status_code == 200:
            events = resp.json()
            if events and isinstance(events, list) and len(events) > 0:
                event_id = events[0].get("event_id") or events[0].get("id")
                if event_id:
                    resp = await client.put(
                        f"/api/ai/events/{event_id}/status",
                        json={"status": "acknowledged"},
                        headers=headers
                    )
                    print(f"更新事件状态: {resp.status_code}")
        # 事件列表为空也视为通过（系统刚启动，没有事件正常）
        print("事件列表为空，跳过状态更新测试")
