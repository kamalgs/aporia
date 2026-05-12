import json
import uuid
from datetime import datetime, timezone

from app.domain.learner import Learner, LearnerCreate
from app.store.db import connection


async def insert(data: LearnerCreate) -> Learner:
    now = datetime.now(timezone.utc)
    learner_id = str(uuid.uuid4())
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO learners (id, name, cohort_tags, created_at, updated_at)
                VALUES (%s, %s, %s::jsonb, %s, %s)
                """,
                (learner_id, data.name, json.dumps(data.cohort_tags), now, now),
            )
        await conn.commit()
    return Learner(
        id=learner_id,
        name=data.name,
        cohort_tags=data.cohort_tags,
        portrait_md="",
        traits={},
        program_states={},
        created_at=now,
        updated_at=now,
    )


async def update_program_state(
    learner_id: str,
    program_id: str,
    skill_id: str,
    skill_state: dict,
) -> Learner:
    """Patch program_states[program_id][skill_id] for the given learner."""
    now = datetime.now(timezone.utc)
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE learners
                SET program_states = jsonb_set(
                    jsonb_set(
                        program_states,
                        %s::text[],
                        COALESCE(program_states->%s, '{}'::jsonb),
                        true
                    ),
                    %s::text[],
                    %s::jsonb,
                    true
                ),
                updated_at = %s
                WHERE id = %s
                """,
                (
                    [program_id],
                    program_id,
                    [program_id, skill_id],
                    json.dumps(skill_state),
                    now,
                    learner_id,
                ),
            )
        await conn.commit()
    learner = await get(learner_id)
    assert learner is not None
    return learner


async def get(learner_id: str) -> Learner | None:
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, cohort_tags, portrait_md, traits, program_states, "
                "created_at, updated_at FROM learners WHERE id = %s",
                (learner_id,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return Learner(
        id=row[0],
        name=row[1],
        cohort_tags=row[2],
        portrait_md=row[3],
        traits=row[4],
        program_states=row[5],
        created_at=row[6],
        updated_at=row[7],
    )
