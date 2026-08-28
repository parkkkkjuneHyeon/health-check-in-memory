from fastapi.testclient import TestClient

from app.main import app


def test_health_and_swagger_are_available():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        dashboard = client.get("/")
        openapi = client.get("/openapi.json").json()

    assert dashboard.status_code == 200
    assert "Health Check Dashboard" in dashboard.text
    assert openapi["info"]["title"] == "인메모리 서버 헬스 체크 API"
    assert "/monitors" in openapi["paths"]
    assert "/recipients" in openapi["paths"]
    assert openapi["components"]["schemas"]["EmailConfigInput"]["properties"]["password"]["writeOnly"] is True
    assert openapi["components"]["schemas"]["AuthConfigInput"]["properties"]["login_payload"]["writeOnly"] is True


def test_monitor_api_hides_auth_secret():
    payload = {
        "name": "주문 API",
        "url": "https://api.example.internal/health",
        "auth": {
            "type": "JWT_LOGIN",
            "login_url": "https://api.example.internal/login",
            "login_payload": {"username": "monitor", "password": "secret"},
            "token_response_path": "access_token",
        },
    }
    with TestClient(app) as client:
        response = client.post("/monitors", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert "login_payload" not in body["auth"]
        assert "secret" not in response.text
