from fastapi.testclient import TestClient

from app.main import create_app


def test_anonymous_cookie_private_access_and_internal_auth(store, settings):
    with TestClient(create_app(settings, store)) as first:
        response = first.get("/v1/session")
        assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=lax" in response.headers["set-cookie"]
        assert first.get("/internal/v1/cases/not-a-case").status_code == 401
        request = {"issueId": "roads-pothole", "location": {"municipalityId": "milton-town", "upperTierId": "halton-region", "fixtureId": "halton-regional-road", "incidentAddress": "Regional Road 25 at Louis St. Laurent Avenue, Milton", "confirmed": True}, "answers": {}}
        created = first.post("/v1/cases", json=request)
        assert created.status_code == 201, created.text
        case = created.json()
        assert first.get(f"/v1/cases/{case['id']}").status_code == 200
        with TestClient(create_app(settings, store)) as second:
            assert second.get(f"/v1/cases/{case['id']}").status_code == 404
            assert second.get(f"/v1/cases/{case['id']}/evidence").status_code == 404
        assert first.post("/v1/cases", json=request, headers={"origin": "https://malicious.example"}).status_code == 403


def test_inactive_http_bypass_and_schema_are_truthful(store, settings):
    with TestClient(create_app(settings, store)) as client:
        assert client.get("/healthz").json()["database"] == "ready"
        assert len(client.get("/v1/catalogue").json()["categories"]) == 9
        assert client.get("/v1/questions/waste-missed-collection").status_code == 404
        request = {"issueId": "waste-missed-collection", "location": {"municipalityId": "milton-town", "upperTierId": "halton-region", "fixtureId": "halton-regional-road", "incidentAddress": "Synthetic address", "confirmed": True}, "answers": {}}
        assert client.post("/v1/cases", json=request).status_code == 422
        assert store.db.cases.count_documents({}) == 0
        assert client.get("/openapi.json").json()["components"]["schemas"]["CaseView"]
