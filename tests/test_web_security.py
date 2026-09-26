from fastapi.testclient import TestClient

from panelprimepasar.api import app


def test_admin_shell_and_assets_have_security_headers() -> None:
    with TestClient(app) as client:
        response = client.get("/admin/ui")
        assert response.status_code == 200
        assert 'lang="fa" dir="rtl"' in response.text
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Cache-Control"] == "no-store"
        assert "script-src 'self'" in response.headers["Content-Security-Policy"]
        assert client.get("/admin/assets/admin.js").status_code == 200
        assert client.get("/admin/assets/admin.css").status_code == 200


def test_webhook_unconfigured_is_rejected() -> None:
    with TestClient(app) as client:
        assert client.post("/telegram/webhook", content="not-json").status_code == 503
