import uuid
from datetime import datetime, timezone

from app.domain.tutor import Tutor, TutorCreate
from app.store.db import connection


async def insert(data: TutorCreate) -> Tutor:
    now = datetime.now(timezone.utc)
    tutor_id = str(uuid.uuid4())
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO tutors (id, name, created_at, updated_at) VALUES (%s, %s, %s, %s)",
                (tutor_id, data.name, now, now),
            )
        await conn.commit()
    return Tutor(id=tutor_id, name=data.name, created_at=now, updated_at=now)


async def get(tutor_id: str) -> Tutor | None:
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, created_at, updated_at FROM tutors WHERE id = %s",
                (tutor_id,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return Tutor(id=row[0], name=row[1], created_at=row[2], updated_at=row[3])
