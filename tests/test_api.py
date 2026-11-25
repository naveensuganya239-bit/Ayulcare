import pytest


def test_csrf_enforced(client):
    r = client.post("/api/auth/login", json={"email": "a@b.co", "password": "x"})
    assert r.status_code == 403


def test_register_requires_terms(api):
    r = api.post("/api/auth/register", {"email": "x@example.com", "password": "Str0ngPassw0rd!", "consent_terms": False})
    assert r.status_code == 400


def test_chat_requires_consent(api):
    api.post("/api/auth/register", {"email": "nc@example.com", "password": "Str0ngPassw0rd!", "consent_terms": True})
    assert api.post("/api/chat/start").status_code == 403


def test_emergency_flow_no_remedies(user, monkeypatch):
    gemini = user.c.application.extensions["svc"].gemini
    monkeypatch.setattr(gemini, "api_key", "test-key")
    monkeypatch.setattr(gemini, "extract", lambda *args: pytest.fail("red flags must bypass Gemini"))
    cid = user.post("/api/chat/start").get_json()["id"]
    r = user.post(f"/api/chat/{cid}/message", {"text": "I have severe chest pain and difficulty breathing"}).get_json()
    p = r["replies"][0]["payload"]
    assert p["type"] == "emergency" and r["risk_level"] == "high" and "remedies" not in p


def test_followup_does_not_initialize_retrieval(user, monkeypatch):
    svc = user.c.application.extensions["svc"]
    monkeypatch.setattr(svc, "ensure_ready", lambda: pytest.fail("retrieval should not load for follow-up"))
    cid = user.post("/api/chat/start").get_json()["id"]

    r = user.post(f"/api/chat/{cid}/message", {"text": "I have a cough"}).get_json()

    assert r["replies"][0]["payload"]["type"] == "followup"


def test_voice_synthesis_returns_local_audio(user, monkeypatch):
    svc = user.c.application.extensions["svc"]
    monkeypatch.setattr(svc.tts, "synthesize", lambda text, language: b"RIFF-audio")

    r = user.post(
        "/api/voice/synthesize",
        {"text": "வணக்கம்", "language": "ta"},
    )

    assert r.status_code == 200
    assert r.mimetype == "audio/wav"
    assert r.headers["Cache-Control"] == "no-store"
    assert r.data == b"RIFF-audio"


def test_voice_synthesis_rejects_unsupported_language(user):
    r = user.post(
        "/api/voice/synthesize",
        {"text": "hello", "language": "en"},
    )

    assert r.status_code == 400


def test_followup_then_assessment_with_sources(user):
    cid = user.post("/api/chat/start").get_json()["id"]
    r = user.post(f"/api/chat/{cid}/message", {"text": "I have a mild cough and sore throat for 2 days"}).get_json()
    assert r["replies"][0]["payload"]["type"] == "followup"        # asks warning-sign screen, not a remedy
    assert r["replies"][0]["payload"]["key"] == "warning"
    r = user.post(f"/api/chat/{cid}/message", {"text": "no"}).get_json()
    last = r["replies"][-1]["payload"]
    # either more clarification (cough type) or the assessment; drive to assessment
    while last["type"] == "followup":
        r = user.post(f"/api/chat/{cid}/message", {"text": "dry, mild"}).get_json()
        last = r["replies"][-1]["payload"]
    assert last["type"] == "assessment" and last["risk"]["level"] in ("low", "medium")
    for rem in last["remedies"]:
        assert rem["author"] and rem["book"] and rem["record_id"]
        assert rem["dataset_risk"] != "High"
    assert last["followup_text"]


def test_tamil_input_gets_tamil_reply(user):
    cid = user.post("/api/chat/start").get_json()["id"]
    r = user.post(f"/api/chat/{cid}/message", {"text": "எனக்கு 2 நாட்களாக இருமல் உள்ளது"}).get_json()
    assert r["language"] == "ta"
    assert any("\u0b80" <= ch <= "\u0bff" for ch in r["replies"][0]["text"])


def test_isolation_between_users(app, user):
    cid = user.post("/api/chat/start").get_json()["id"]
    other = app.test_client()
    from tests.conftest import Api
    o = Api(other)
    o.post("/api/auth/register", {"email": "other@example.com", "password": "Str0ngPassw0rd!", "consent_terms": True})
    o.post("/api/profile/consents", {"health": True})
    assert o.get(f"/api/chat/{cid}").status_code == 404


def test_researcher_endpoints_forbidden_for_users(user):
    assert user.get("/api/research/summary").status_code == 403


def test_feedback_worse_escalates(user):
    cid = user.post("/api/chat/start").get_json()["id"]
    r = user.post("/api/feedback", {"consultation_id": cid, "outcome": "worse", "helpfulness": 2}).get_json()
    assert r["escalate"] and r["advice"]


def test_account_deletion_removes_data(app, user):
    user.post("/api/chat/start")
    assert user.delete("/api/account", {"password": "wrong"}).status_code == 403
    assert user.delete("/api/account", {"password": "Str0ngPassw0rd!"}).status_code == 200
    assert user.get("/api/profile").status_code == 401
    from app.models import User
    with app.app_context():
        assert User.query.filter_by(email=user.email).first() is None
