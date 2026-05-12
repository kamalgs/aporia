import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import TypeAdapter

from app.domain.events import TranscriptEvent
from app.domain.session import Session, SessionCreate
from app.store.db import connection


_event_adapter: TypeAdapter[TranscriptEvent] = TypeAdapter(TranscriptEvent)


def _parse_transcript(raw: list[Any]) -> list[TranscriptEvent]:
    return [_event_adapter.validate_python(e) for e in raw]


async def insert(data: SessionCreate) -> Session:
    now = datetime.now(timezone.utc)
    session_id = str(uuid.uuid4())
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO sessions (id, learner_id, program_id, started_at)
                VALUES (%s, %s, %s, %s)
                """,
                (session_id, data.learner_id, data.program_id, now),
            )
        await conn.commit()
    return Session(
        id=session_id,
        learner_id=data.learner_id,
        program_id=data.program_id,
        status="active",
        started_at=now,
        ended_at=None,
        transcript=[],
        summary_md="",
    )


async def get(session_id: str) -> Session | None:
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, learner_id, program_id, status, started_at, ended_at, "
                "transcript, summary_md FROM sessions WHERE id = %s",
                (session_id,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return Session(
        id=row[0],
        learner_id=row[1],
        program_id=row[2],
        status=row[3],
        started_at=row[4],
        ended_at=row[5],
        transcript=_parse_transcript(row[6]),
        summary_md=row[7],
    )


async def append_event(session_id: str, event: TranscriptEvent) -> None:
    event_json = json.dumps(event.model_dump(mode="json"))
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE sessions SET transcript = transcript || %s::jsonb WHERE id = %s",
                (f"[{event_json}]", session_id),
            )
        await conn.commit()


async def end(session_id: str, summary_md: str = "") -> Session | None:
    now = datetime.now(timezone.utc)
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE sessions SET status = 'ended', ended_at = %s, summary_md = %s "
                "WHERE id = %s",
                (now, summary_md, session_id),
            )
        await conn.commit()
    return await get(session_id)
