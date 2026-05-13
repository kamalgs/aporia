import asyncio

import pytest

from app.event_stream import publish, subscribe


@pytest.mark.asyncio
async def test_subscribe_replays_existing_events() -> None:
    replay = [{"kind": "learner_text", "text": "hello"}]
    received = []

    async def collect():
        async for event in subscribe("sess-replay-1", replay):
            received.append(event)
            break

    await collect()
    assert received == replay


@pytest.mark.asyncio
async def test_publish_reaches_subscriber() -> None:
    received = []

    async def collect():
        async for event in subscribe("sess-pub-1", []):
            received.append(event)
            break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await publish("sess-pub-1", {"kind": "utterance", "text": "hi"})
    await task
    assert len(received) == 1
    assert received[0]["kind"] == "utterance"


@pytest.mark.asyncio
async def test_publish_to_multiple_subscribers() -> None:
    received_a: list[dict] = []
    received_b: list[dict] = []

    async def collect(store: list):
        async for event in subscribe("sess-multi-1", []):
            store.append(event)
            break

    task_a = asyncio.create_task(collect(received_a))
    task_b = asyncio.create_task(collect(received_b))
    await asyncio.sleep(0)
    await publish("sess-multi-1", {"kind": "turn_signal", "on_target": True})
    await task_a
    await task_b
    assert received_a[0]["on_target"] is True
    assert received_b[0]["on_target"] is True


@pytest.mark.asyncio
async def test_no_cross_session_leakage() -> None:
    received = []

    async def collect():
        async for event in subscribe("sess-iso-A", []):
            received.append(event)
            break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await publish("sess-iso-B", {"kind": "utterance", "text": "wrong session"})
    await publish("sess-iso-A", {"kind": "utterance", "text": "right session"})
    await task
    assert received[0]["text"] == "right session"
