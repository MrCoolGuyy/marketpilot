import pytest
from fastapi.testclient import TestClient
from marketpilot.dashboard.server import app, get_system_status

client = TestClient(app)

def test_dashboard_index():
    response = client.get("/")
    assert response.status_code == 200
    assert b"MarketPilot Mission Control" in response.content

def test_api_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "rc_version" in data

def test_fragments_health():
    response = client.get("/fragments/health")
    assert response.status_code == 200
    assert b"Daemon Status" in response.content
