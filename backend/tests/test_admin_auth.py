from fastapi.testclient import TestClient

from app.main import app


def test_admin_endpoints_require_api_key() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/admin/products")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid admin API key"}
