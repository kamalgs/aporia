"""initial_schema

Revision ID: 0001
Revises: 
Create Date: 2026-05-12 20:38:31.036528

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS learners (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            cohort_tags     JSONB NOT NULL DEFAULT '[]'::jsonb,
            portrait_md     TEXT NOT NULL DEFAULT '',
            traits          JSONB NOT NULL DEFAULT '{}'::jsonb,
            program_states  JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id              TEXT PRIMARY KEY,
            learner_id      TEXT NOT NULL REFERENCES learners(id) ON DELETE CASCADE,
            program_id      TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'active',
            started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ended_at        TIMESTAMPTZ,
            transcript      JSONB NOT NULL DEFAULT '[]'::jsonb,
            summary_md      TEXT NOT NULL DEFAULT ''
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_learner
        ON sessions (learner_id, started_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS learners")
