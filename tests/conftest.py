import os
import tempfile
from pathlib import Path

import pytest

os.environ["APP_ENV"] = "testing"


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    from app import create_app
    from app.config import TestingConfig
    TestingConfig.INDEX_DIR = tmp_path_factory.mktemp("index")
    TestingConfig.REPORT_DIR = tmp_path_factory.mktemp("reports")
    a = create_app("testing")
    return a


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf(client):
    return client.get("/api/csrf").get_json()["csrf"]


class Api:
    def __init__(self, client):
        self.c, self.tok = client, csrf(client)

    def post(self, url, json=None, **kw):
        r = self.c.post(url, json=json, headers={"X-CSRF-Token": self.tok}, **kw)
        body = r.get_json(silent=True) or {}
        if "csrf" in body:
            self.tok = body["csrf"]
        return r

    def put(self, url, json=None):
        return self.c.put(url, json=json, headers={"X-CSRF-Token": self.tok})

    def delete(self, url, json=None):
        return self.c.delete(url, json=json, headers={"X-CSRF-Token": self.tok})

    def get(self, url):
        return self.c.get(url)


@pytest.fixture()
def api(client):
    return Api(client)


@pytest.fixture()
def user(api):
    import uuid
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    r = api.post("/api/auth/register", {"email": email, "password": "Str0ngPassw0rd!", "consent_terms": True})
    assert r.status_code == 201, r.get_json()
    r = api.post("/api/profile/consents", {"health": True, "ai_context": False, "research": True})
    assert r.status_code == 200
    api.put("/api/profile", {"name": "Test User", "date_of_birth": "1990-05-01", "gender": "female", "height_cm": 160,
                             "weight_kg": 58, "sleep_hours": 6, "food_preference": "vegetarian", "completed": True})
    api.email = email
    return api
