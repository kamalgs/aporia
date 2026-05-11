"""End-to-end evals against the live deployed FastAPI backend.

These call real REST endpoints and verify the full session completes.
Unlike agent-level evals, they test the FastAPI → LLM → JSON response
path exactly as a user experiences it.
"""

from datetime import datetime

import pytest
from httpx import AsyncClient, Timeout

BASE_URL = "https://aporia.gkamal.online"
TIMEOUT = Timeout(120.0, connect=15.0)


@pytest.fixture(scope="module")
async def api_client():
    async with AsyncClient(timeout=Timeout(120.0, connect=30.0)) as client:
        # health check with generous timeout — the LLM takes ~20-30s cold
        try:
            resp = await client.post(f"{BASE_URL}/sessions")
            if resp.status_code != 200:
                pytest.skip(f"API not responsive: {resp.status_code}")
        except Exception as e:
            pytest.skip(f"API unreachable: {type(e).__name__}")
        yield client


async def _start_session() -> dict:
    async with AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{BASE_URL}/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert "session_id" in body
        assert "step" in body
        return body


async def _answer(session_id: str, text: str) -> dict:
    async with AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/sessions/{session_id}/answer",
            json={"text": text},
        )
        assert resp.status_code == 200
        return resp.json()


@pytest.mark.asyncio
async def test_e2e_perfect_student_completes():
    """Always-correct student: should reach complete in ≤10 turns."""
    start = await _start_session()
    sid = start["session_id"]
    step = start["step"]
    phases_seen = [step["phase"]]
    turns = 0
    max_turns = 12

    while step["phase"] != "complete" and turns < max_turns:
        assert step["question"] is not None
        a, b = step["question"]["a"], step["question"]["b"]
        correct = a + b
        step = await _answer(sid, str(correct))
        phases_seen.append(step["phase"])
        turns += 1

    assert step["phase"] == "complete", f"Never reached complete after {turns} turns. Phases: {phases_seen}"
    assert step["question"] is None


@pytest.mark.asyncio
async def test_e2e_omit_carry_student_scaffolds():
    """Student omits carry on diagnostic, gets simpler problems, eventually completes."""
    start = await _start_session()
    sid = start["session_id"]
    step = start["step"]
    phases_seen = [step["phase"]]
    turns = 0
    max_turns = 15

    # Turn 0: wrong (omit carry)
    if step["phase"] == "diagnostic":
        a, b = step["question"]["a"], step["question"]["b"]
        wrong = (a // 10 + b // 10) * 10 + ((a % 10) + (b % 10)) % 10
        step = await _answer(sid, str(wrong))
        phases_seen.append(step["phase"])
        turns += 1
        # should have dropped to targeted
        assert step["phase"] == "targeted", f"Expected targeted after omit-carry, got {step['phase']}"

    while step["phase"] != "complete" and turns < max_turns:
        assert step["question"] is not None
        a, b = step["question"]["a"], step["question"]["b"]
        correct = a + b
        step = await _answer(sid, str(correct))
        phases_seen.append(step["phase"])
        turns += 1

    assert step["phase"] == "complete", f"Never reached complete. Phases: {phases_seen}"


@pytest.mark.asyncio
async def test_e2e_place_value_error():
    """Student concatenates digits. Tutor must diagnose, scaffold, eventually complete."""
    start = await _start_session()
    sid = start["session_id"]
    step = start["step"]
    a, b = step["question"]["a"], step["question"]["b"]
    wrong = int(f"{a}{b}")
    step = await _answer(sid, str(wrong))
    assert step["phase"] == "targeted"
    assert step["question"] is not None
    # Answer all subsequent questions correctly until complete
    turns = 1
    while step["phase"] != "complete" and turns < 12:
        a, b = step["question"]["a"], step["question"]["b"]
        step = await _answer(sid, str(a + b))
        turns += 1
    assert step["phase"] == "complete"


@pytest.mark.asyncio
async def test_e2e_session_state_preserved():
    """Verify /sessions/{id} returns the same turn history we built."""
    start = await _start_session()
    sid = start["session_id"]

    # Two answers
    step1 = await _answer(sid, "51")
    step2 = await _answer(sid, "11")

    async with AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{BASE_URL}/sessions/{sid}")
        assert resp.status_code == 200
        state = resp.json()

    assert state["session_id"] == sid
    assert len(state["turns"]) >= 5  # tutor + student + tutor + student + tutor
    tutor_count = sum(1 for t in state["turns"] if t["role"] == "tutor")
    student_count = sum(1 for t in state["turns"] if t["role"] == "student")
    assert tutor_count == student_count + 1  # tutor always speaks first
