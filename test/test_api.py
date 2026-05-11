from fastapi.testclient import TestClient

from app.main import app, get_agent, get_store
from app.agent import FakeAgent
from app.session_store import SessionStore


class _TestDeps:
    store = SessionStore()
    agent = FakeAgent(seed=42)

client = TestClient(app)


def _use_deps():
    _TestDeps.store = SessionStore()
    _TestDeps.agent = FakeAgent(seed=42)
    app.dependency_overrides[get_store] = lambda: _TestDeps.store
    app.dependency_overrides[get_agent] = lambda: _TestDeps.agent


def test_start_session_gives_diagnostic_problem():
    _use_deps()
    resp = client.post("/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"]
    step = body["step"]
    assert step["phase"] == "diagnostic"
    assert step["question"]["a"] == 88
    assert step["question"]["b"] == 99


def test_correct_diagnostic_moves_to_mastery():
    _use_deps()
    create = client.post("/sessions").json()
    sid = create["session_id"]
    # correct answer to 88+99
    resp = client.post(f"/sessions/{sid}/answer", json={"text": "187"})
    assert resp.status_code == 200
    step = resp.json()
    assert step["phase"] == "mastery"
    assert step["evaluation"]["is_correct"] is True
    assert step["question"] is not None


def test_omit_carry_diagnosed_and_pivots_to_targeted():
    _use_deps()
    create = client.post("/sessions").json()
    sid = create["session_id"]
    # omit carry: 88+99 without carrying = 177
    resp = client.post(f"/sessions/{sid}/answer", json={"text": "177"})
    assert resp.status_code == 200
    step = resp.json()
    assert step["phase"] == "targeted"
    assert step["evaluation"]["is_correct"] is False
    assert "omit_carry" in step["evaluation"]["misconceptions"]
    assert step["question"] is not None


def test_targeted_mastery_completes_session():
    _use_deps()
    create = client.post("/sessions").json()
    sid = create["session_id"]

    # 1. diagnostic wrong (omit carry)
    step = client.post(f"/sessions/{sid}/answer", json={"text": "177"}).json()
    assert step["phase"] == "targeted"

    # Scaffolded steps: may take 1-4 correct answers to reach mastery
    turns = 0
    while step["phase"] == "targeted" and turns < 10:
        a, b = step["question"]["a"], step["question"]["b"]
        step = client.post(f"/sessions/{sid}/answer", json={"text": str(a + b)}).json()
        turns += 1

    assert step["phase"] == "mastery"
    a, b = step["question"]["a"], step["question"]["b"]
    # mastery correct → complete
    step = client.post(f"/sessions/{sid}/answer", json={"text": str(a + b)}).json()
    assert step["phase"] == "complete"
    assert step["question"] is None


def test_direct_mastery_completes_session():
    _use_deps()
    create = client.post("/sessions").json()
    sid = create["session_id"]

    # 1. diagnostic correct
    step = client.post(f"/sessions/{sid}/answer", json={"text": "187"}).json()
    assert step["phase"] == "mastery"
    a, b = step["question"]["a"], step["question"]["b"]
    # 2. mastery correct
    step = client.post(f"/sessions/{sid}/answer", json={"text": str(a + b)}).json()
    assert step["phase"] == "complete"
    assert step["question"] is None
