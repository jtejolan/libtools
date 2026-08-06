"""add session workspace fields

Revision ID: e93f1a6b2c47
Revises: d7e3b91c4a20
Create Date: 2026-08-05 22:00:00.000000

"""
from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e93f1a6b2c47"
down_revision: Union[str, None] = "d7e3b91c4a20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bookclub_meetings",
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="planned",
            nullable=False,
        ),
    )
    op.add_column(
        "bookclub_meetings",
        sa.Column("discussion_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "bookclub_participation",
        sa.Column("notes", sa.Text(), nullable=True),
    )

    connection = op.get_bind()
    existing_questions: dict[int, list[str]] = defaultdict(list)
    rows = connection.execute(
        sa.text(
            "SELECT meeting_id, text FROM bookclub_discussion_questions "
            "ORDER BY meeting_id, position"
        )
    )
    for meeting_id, text in rows:
        existing_questions[meeting_id].append(text)
    for meeting_id, questions in existing_questions.items():
        connection.execute(
            sa.text(
                "UPDATE bookclub_meetings "
                "SET discussion_notes = :discussion_notes WHERE id = :meeting_id"
            ),
            {
                "meeting_id": meeting_id,
                "discussion_notes": "\n\n".join(questions),
            },
        )


def downgrade() -> None:
    op.drop_column("bookclub_participation", "notes")
    op.drop_column("bookclub_meetings", "discussion_notes")
    op.drop_column("bookclub_meetings", "status")
