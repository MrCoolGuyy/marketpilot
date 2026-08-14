import pytest
from httpx import AsyncClient, ASGITransport
from marketpilot.dashboard.server import app

@pytest.mark.asyncio
async def test_dashboard_index_route():
    """Verify that the dashboard root route loads correctly."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Start the lifespan
        async with app.router.lifespan_context(app):
            response = await client.get("/")
            assert response.status_code == 200
            assert "html" in response.headers.get("content-type", "").lower()
