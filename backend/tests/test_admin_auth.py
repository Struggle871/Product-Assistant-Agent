import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize(
    "path,method",
    [
        ("/products", "GET"),
        ("/catalog/seed", "POST"),
        ("/trusted-sources", "GET"),
        ("/documents", "GET"),
        ("/documents/document-1", "GET"),
        ("/documents/document-1/archive", "POST"),
        ("/ingestion-jobs", "GET"),
        ("/ingestion-jobs/job-1", "GET"),
        ("/ingestion-jobs/job-1/retry", "POST"),
        ("/index-versions", "GET"),
    ],
)
@pytest.mark.parametrize("headers", [{}, {"X-Admin-API-Key": "invalid"}])
def test_admin_endpoints_require_api_key(path: str, method: str, headers: dict[str, str]) -> None:
    with TestClient(app) as client:
        response = client.request(method, f"/api/v1/admin{path}", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid admin API key"}
