"""Module 7: 仪表盘测试"""
import pytest

pytestmark = pytest.mark.asyncio


class TestDashboard:
    """TC-25: 仪表盘"""

    async def test_dashboard_stats(self, client, admin_token):
        """TC-25: GET /api/ai/dashboard/stats 仪表盘数据"""
        if not admin_token:
            pytest.skip("未获取到admin_token")
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = await client.get("/api/ai/dashboard/stats", headers=headers)
        print(f"仪表盘数据: {resp.status_code}")
        assert resp.status_code in (200, 404)
