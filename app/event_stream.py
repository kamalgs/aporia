import asyncio
from collections import defaultdict
from typing import AsyncGenerator

_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)


async def publish(session_id: str, event: dict) -> None:
    for q in _subscribers.get(session_id, []):
        await q.put(event)


async def subscribe(
    session_id: str,
    replay: list[dict],
) -> AsyncGenerator[dict, None]:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[session_id].append(q)
    try:
        for event in replay:
            yield event
        while True:
            event = await asyncio.wait_for(q.get(), timeout=30.0)
            yield event
    except asyncio.TimeoutError:
        pass
    finally:
        _subscribers[session_id].remove(q)
